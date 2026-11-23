from __future__ import annotations

import json
import os
import platform
import re
import sys
import time
import urllib.request

import hippos_flatpak_apps
import hippos_webapps

_DEFAULT_CATALOG_URL = "https://hippos-linux.org/store/content-catalog.json"


def _read_sysconf(key):
    path = "/userdata/system/hippos.conf"
    try:
        for line in open(path):
            k, _, v = line.strip().partition("=")
            if k.strip() == key:
                return v.strip()
    except FileNotFoundError:
        pass
    return None


CATALOG_URL = _read_sysconf("content.catalog_url") or _DEFAULT_CATALOG_URL
STATE_DIR = "/userdata/system/hippos-store"
STATE_FILE = os.path.join(STATE_DIR, "installed.json")
CACHE_DIR = os.path.join(STATE_DIR, "cache")
DEB_ARCH = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
RECOMP_CATALOG_URL = "https://recomplauncher.com/pc-catalog.json"
RECOMP_CACHE = os.path.join(CACHE_DIR, "recomp-catalog.json")
RECOMP_MAX_AGE_S = 6 * 3600
RECOMP_PREFIX = "recomp::"
ARM_ASSET_WORDS = ("aarch64", "arm64")
GITHUB_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def load_catalog():
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": "hippos-store/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))["packages"]
    except Exception as exc:
        print(f"Error: could not fetch catalog: {exc}", file=sys.stderr)
        return []


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def catalog_section(pkg):
    if pkg.get("section"):
        return pkg["section"]
    if pkg.get("category") in ("apps", "webapps"):
        return "Apps"
    if pkg.get("type") == "installer":
        return "Launchers"
    if pkg.get("scummvm_id"):
        return "ScummVM classics"
    if pkg.get("category") == "ports":
        return "Open-source games"
    return "RetroArch"


def for_this_machine(pkg):
    arch = pkg.get("arch", "")
    if pkg.get("type") == "deb" and DEB_ARCH not in pkg.get("deb", {}):
        return False
    if pkg.get("type") == "archive" and DEB_ARCH not in pkg.get("archive", {}):
        return False
    return not arch or arch == DEB_ARCH


def is_installed(pkg, state):
    if pkg.get("type") == "webapp":
        url = hippos_webapps.normalise_url(pkg.get("webapp_url", ""))
        return any(app.url == url for app in hippos_webapps.load_webapps())
    if pkg.get("type") == "flatpak":
        return hippos_flatpak_apps.installed(pkg.get("flatpak_id", ""))
    if pkg.get("type") == "script":
        return os.path.exists(pkg["installed_path"])
    return pkg["id"] in state


def load_recomp_catalog():
    try:
        fresh = time.time() - os.path.getmtime(RECOMP_CACHE) < RECOMP_MAX_AGE_S
    except OSError:
        fresh = False
    if not fresh:
        req = urllib.request.Request(RECOMP_CATALOG_URL, headers={"User-Agent": "hippos-store/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            json.loads(data)
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(RECOMP_CACHE + ".tmp", "wb") as f:
                f.write(data)
            os.replace(RECOMP_CACHE + ".tmp", RECOMP_CACHE)
        except (OSError, ValueError) as exc:
            print(f"WARNING: could not fetch the recomp catalog: {exc}", file=sys.stderr)
    try:
        with open(RECOMP_CACHE, encoding="utf-8") as f:
            return json.load(f).get("apps", [])
    except (OSError, ValueError):
        return []


def recomp_linux_pattern(entry):
    assets = entry.get("assets")
    pattern = assets.get("linux") if isinstance(assets, dict) else None
    if not pattern or not GITHUB_REPO.match(entry.get("repo", "")):
        return None
    arm = any(word in pattern.lower() for word in ARM_ASSET_WORDS)
    return pattern if arm == (DEB_ARCH == "arm64") else None

