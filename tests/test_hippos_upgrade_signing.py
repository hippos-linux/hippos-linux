import base64
import importlib.machinery
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

LIB = Path(__file__).resolve().parents[1] / "overlays/rootfs/usr/lib/hippos"
sys.path.insert(0, str(LIB))


def _load_hippos_upgrade():
    loader = importlib.machinery.SourceFileLoader("hippos_upgrade_signing", str(LIB / "hippos-upgrade"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


hu = _load_hippos_upgrade()


def make_key(directory, name):
    private = Path(directory) / f"{name}.key"
    public = Path(directory) / "keys" / f"{name}.pem"
    public.parent.mkdir(exist_ok=True)
    subprocess.run(["openssl", "genpkey", "-algorithm", "ed25519", "-out", private], check=True)
    subprocess.run(["openssl", "pkey", "-in", private, "-pubout", "-out", public], check=True)
    return private


def sign(private, body):
    with tempfile.NamedTemporaryFile() as manifest:
        manifest.write(body)
        manifest.flush()
        raw = subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", private, "-in", manifest.name],
                             check=True, capture_output=True).stdout
    return base64.b64encode(raw).decode()


class FakeResponse:
    def __init__(self, body, signature):
        self.body = body
        self.headers = {"X-HippOS-Signature": signature} if signature else {}

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ManifestSignatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.private = make_key(self.tmp.name, "hippos")
        keys_dir = mock.patch.object(hu, "UPDATE_KEYS_DIR", str(Path(self.tmp.name) / "keys"))
        keys_dir.start()
        self.addCleanup(keys_dir.stop)
        self.addCleanup(self.tmp.cleanup)
        self.body = json.dumps({"version": "0.7.4", "payloads": {}}).encode()

    def test_manifest_signed_with_a_shipped_key_is_accepted(self):
        self.assertTrue(hu.signed_by_hippos(self.body, sign(self.private, self.body)))

    def test_changed_manifest_is_rejected(self):
        signature = sign(self.private, self.body)
        self.assertFalse(hu.signed_by_hippos(self.body.replace(b"0.7.4", b"0.7.5"), signature))

    def test_missing_or_malformed_signature_is_rejected(self):
        self.assertFalse(hu.signed_by_hippos(self.body, ""))
        self.assertFalse(hu.signed_by_hippos(self.body, "not base64!"))

    def test_signature_from_an_unknown_key_is_rejected(self):
        other = make_key(self.tmp.name, "other")
        (Path(self.tmp.name) / "keys" / "other.pem").unlink()
        self.assertFalse(hu.signed_by_hippos(self.body, sign(other, self.body)))

    def test_any_shipped_key_can_sign(self):
        second = make_key(self.tmp.name, "second")
        self.assertTrue(hu.signed_by_hippos(self.body, sign(second, self.body)))

    def test_fetch_returns_signed_manifest_and_skips_unsigned(self):
        signed = FakeResponse(self.body, sign(self.private, self.body))
        with mock.patch.object(hu.urllib.request, "urlopen", return_value=signed):
            self.assertEqual(hu._fetch_first_manifest(["https://example.invalid/m.json"])["version"], "0.7.4")
        with mock.patch.object(hu.urllib.request, "urlopen", return_value=FakeResponse(self.body, "")), \
                mock.patch.object(hu, "log"):
            self.assertIsNone(hu._fetch_first_manifest(["https://example.invalid/m.json"]))


class PayloadChecksumTests(unittest.TestCase):
    def test_payload_without_checksum_is_not_downloaded(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(hu.urllib.request, "urlopen") as urlopen:
            with self.assertRaises(hu.DownloadError):
                hu.fetch_archive("https://example.invalid/rootfs", str(Path(tmp) / "rootfs.tar.zst"), "")
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
