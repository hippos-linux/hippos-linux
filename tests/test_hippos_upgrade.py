"""Unit tests for overlays/rootfs/usr/lib/hippos/hippos-upgrade.

The script has no .py extension (it's installed straight into the image as
a CLI tool), so it's loaded here via SourceFileLoader rather than a normal
import. Only pure functions are exercised — nothing here touches btrfs,
GRUB, the network, or root-owned paths, so it's safe to run on any dev
machine.
"""

import importlib.machinery
import importlib.util
import unittest
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "overlays" / "rootfs" / "usr" / "lib" / "hippos" / "hippos-upgrade"
)


def _load_hippos_upgrade():
    loader = importlib.machinery.SourceFileLoader("hippos_upgrade", str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


hu = _load_hippos_upgrade()


class VerTupleTests(unittest.TestCase):
    def test_equal_length_versions_compare_normally(self):
        self.assertLess(hu.ver_tuple("0.5.1"), hu.ver_tuple("0.5.10"))
        self.assertGreater(hu.ver_tuple("0.5.2"), hu.ver_tuple("0.5.1"))

    def test_short_and_long_forms_of_same_version_are_equal(self):
        # Regression test: ver_tuple used to right-pad *after* truncating,
        # so "1.2" (5-tuple) and "1.2.0" (6-tuple) compared unequal even
        # though they name the same version.
        self.assertEqual(hu.ver_tuple("1.2"), hu.ver_tuple("1.2.0"))
        self.assertEqual(hu.ver_tuple("1"), hu.ver_tuple("1.0.0"))
        self.assertFalse(hu.ver_tuple("1.2") < hu.ver_tuple("1.2.0"))
        self.assertFalse(hu.ver_tuple("1.2.0") < hu.ver_tuple("1.2"))

    def test_v_prefix_is_stripped(self):
        self.assertEqual(hu.ver_tuple("v0.5.1"), hu.ver_tuple("0.5.1"))

    def test_extra_components_beyond_patch_are_ignored(self):
        self.assertEqual(hu.ver_tuple("1.2.3.4"), hu.ver_tuple("1.2.3"))


def _subvol_list_output(names) -> str:
    """Build fake `btrfs subvolume list -o` output for the given subvol names."""
    return "\n".join(
        f"ID {260 + i} gen {900 + i} top level 5 path {name}"
        for i, name in enumerate(names)
    )


class SortDeploymentNamesTests(unittest.TestCase):
    def test_sorts_numerically_not_lexicographically(self):
        names = ["@rootfs-0.5.10", "@rootfs-0.5.2", "@rootfs-0.5.1"]
        self.assertEqual(
            hu.sort_deployment_names(names),
            ["@rootfs-0.5.1", "@rootfs-0.5.2", "@rootfs-0.5.10"],
        )

    def test_kernel_snapshots_sort_after_os_deployments(self):
        # Kernel snapshot names carry a kernel version that ver_tuple can't
        # parse; they must sort last so they become the boot-counter fallback.
        names = ["@rootfs-kernel-6.12.1-hippos", "@rootfs", "@rootfs-0.6.3", "@rootfs-0.6.2"]
        self.assertEqual(
            hu.sort_deployment_names(names),
            ["@rootfs-0.6.2", "@rootfs-0.6.3", "@rootfs", "@rootfs-kernel-6.12.1-hippos"],
        )


class ParseDeploymentNamesTests(unittest.TestCase):
    def test_filters_to_rootfs_names_and_sorts_numerically(self):
        output = _subvol_list_output(
            ["@userdata", "@rootfs", "@rootfs-0.5.10", "@rootfs-0.5.2", "@overlay", "@rootfs.new"])
        self.assertEqual(
            hu.parse_deployment_names(output),
            ["@rootfs-0.5.2", "@rootfs-0.5.10", "@rootfs"],
        )

    def test_empty_output_yields_empty_list(self):
        self.assertEqual(hu.parse_deployment_names(""), [])


class ParseCurrentSubvolTests(unittest.TestCase):
    def test_extracts_subvol_from_overlay_lowerdir(self):
        mounts = (
            "sysfs /sys sysfs rw 0 0\n"
            "/dev/sda2 /run/hippos-btrfs btrfs rw,subvolid=5 0 0\n"
            "overlay / overlay rw,lowerdir=/run/hippos-btrfs/@rootfs-0.5.1,"
            "upperdir=/run/hippos-btrfs/@overlay/upper,"
            "workdir=/run/hippos-btrfs/@overlay/work 0 0\n"
            "/dev/sda3 /userdata btrfs rw,subvol=/@userdata 0 0\n"
        )
        self.assertEqual(hu.parse_current_subvol(mounts), "@rootfs-0.5.1")

    def test_falls_back_to_bare_rootfs_when_no_overlay_root(self):
        mounts = "/dev/sda2 / btrfs rw,subvol=/@rootfs 0 0\n"
        self.assertEqual(hu.parse_current_subvol(mounts), "@rootfs")


class PlanApplyTests(unittest.TestCase):
    """These assert the actual prune/rename *decisions* — the externally
    meaningful behaviour of cmd_apply — not that some mock got called."""

    def test_running_rootfs_is_renamed_to_its_version(self):
        plan = hu.plan_apply(
            running="@rootfs", cur_version="0.6.8",
            existing_deployments=["@rootfs"],
        )
        self.assertEqual(plan.retire_running_as, "@rootfs-0.6.8")
        self.assertEqual(plan.prune, [])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.6.8", "@rootfs"])

    def test_steady_state_prunes_the_previous_rollback(self):
        plan = hu.plan_apply(
            running="@rootfs", cur_version="0.6.9",
            existing_deployments=["@rootfs-0.6.8", "@rootfs"],
        )
        self.assertEqual(plan.prune, ["@rootfs-0.6.8"])
        self.assertEqual(plan.retire_running_as, "@rootfs-0.6.9")
        self.assertEqual(plan.final_deployments, ["@rootfs-0.6.9", "@rootfs"])

    def test_versioned_deployment_from_the_old_scheme_keeps_its_name(self):
        # Systems updated before @rootfs was always the newest run from
        # @rootfs-<version>, with the install-time @rootfs left behind.
        plan = hu.plan_apply(
            running="@rootfs-0.6.7", cur_version="0.6.7",
            existing_deployments=["@rootfs-0.6.6", "@rootfs-0.6.7", "@rootfs"],
        )
        self.assertIsNone(plan.retire_running_as)
        self.assertEqual(plan.prune, ["@rootfs-0.6.6", "@rootfs"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.6.7", "@rootfs"])

    def test_update_while_rolled_back_replaces_the_newer_rootfs(self):
        plan = hu.plan_apply(
            running="@rootfs-0.6.8", cur_version="0.6.8",
            existing_deployments=["@rootfs-0.6.8", "@rootfs"],
        )
        self.assertEqual(plan.prune, ["@rootfs"])
        self.assertIsNone(plan.retire_running_as)

    def test_prune_order_uses_numeric_not_lexicographic_order(self):
        plan = hu.plan_apply(
            running="@rootfs-0.5.10", cur_version="0.5.10",
            existing_deployments=["@rootfs-0.5.2", "@rootfs-0.5.9", "@rootfs-0.5.10"],
        )
        self.assertEqual(plan.prune, ["@rootfs-0.5.2", "@rootfs-0.5.9"])

    def test_os_update_prunes_kernel_snapshots(self):
        plan = hu.plan_apply(
            running="@rootfs", cur_version="0.6.2",
            existing_deployments=["@rootfs", "@rootfs-kernel-6.12.1-hippos"],
        )
        self.assertEqual(plan.prune, ["@rootfs-kernel-6.12.1-hippos"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.6.2", "@rootfs"])


class UpdateSpaceShortfallTests(unittest.TestCase):
    GB = 1024 ** 3
    PAYLOAD = {"size": 2 * GB, "installed_size": 6 * GB}

    def test_fits_with_room_for_archive_extraction_and_reserve(self):
        free = 8 * self.GB + hu.UPDATE_SPACE_RESERVE
        self.assertEqual(hu.update_space_shortfall(free, self.PAYLOAD, False), 0)

    def test_reports_missing_bytes_when_archive_must_still_be_downloaded(self):
        free = 7 * self.GB
        self.assertEqual(
            hu.update_space_shortfall(free, self.PAYLOAD, False),
            1 * self.GB + hu.UPDATE_SPACE_RESERVE,
        )

    def test_cached_archive_no_longer_needs_space(self):
        free = 6 * self.GB + hu.UPDATE_SPACE_RESERVE
        self.assertEqual(hu.update_space_shortfall(free, self.PAYLOAD, True), 0)

    def test_manifest_without_sizes_skips_the_check(self):
        self.assertEqual(hu.update_space_shortfall(0, {"url": "x"}, False), 0)


if __name__ == "__main__":
    unittest.main()


class FirmwareBootTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.efi = self.tmp / "efi"
        self.efi.mkdir()
        (self.efi / "config.txt").write_text("kernel=kernel8.img\n")
        self.btrfs = self.tmp / "btrfs"
        self._deployment("@rootfs", {"7.3.3-hippos": "new", "6.18.62-hippos-lts": "new-lts"})
        self._deployment("@rootfs-0.6.10", {"7.0.12-hippos": "old"})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def _deployment(self, name, kernels):
        boot = self.btrfs / name / "boot"
        boot.mkdir(parents=True)
        for release, tag in kernels.items():
            (boot / f"vmlinuz-{release}").write_text(f"{tag}-kernel")
            (boot / f"initrd.img-{release}").write_text(f"{tag}-initrd")

    def _patch(self, variant="standard", extra_args=()):
        from unittest import mock
        efi = self.efi
        return mock.patch.multiple(
            hu,
            RPI_CONFIG_TXT=str(efi / "config.txt"),
            RPI_TRYBOOT_STATE=str(efi / "hippos-tryboot.json"),
            SYSTEMD_REBOOT_PARAM=str(self.tmp / "reboot-param"),
            RPI_PRIMARY=hu.FirmwareBootSet(str(efi / "kernel8.img"), str(efi / "initramfs8"), str(efi / "cmdline.txt")),
            RPI_TRYBOOT=hu.FirmwareBootSet(str(efi / "kernel8-try.img"), str(efi / "initramfs8-try"), str(efi / "cmdline-try.txt")),
            BTRFS_MNT=str(self.btrfs),
            efi_partition_mounted=lambda: True,
            default_kernel_variant=lambda: variant,
            read_grub_cmdline_args=lambda: list(extra_args),
            log=lambda msg: None,
        )

    def _read(self, name):
        return (self.efi / name).read_text()

    def test_primary_gets_selected_variant_and_cmdline_names_deployment(self):
        with self._patch(extra_args=["usbhid.mousepoll=1"]):
            self.assertTrue(hu.firmware_loads_kernel())
            hu.write_firmware_boot("@rootfs", "abcd-02")
        self.assertEqual(self._read("kernel8.img"), "new-kernel")
        self.assertEqual(self._read("initramfs8"), "new-initrd")
        self.assertEqual(
            self._read("cmdline.txt"),
            "root=PARTUUID=abcd-02 rootfstype=btrfs rootflags=subvol=@rootfs ro quiet splash usbhid.mousepoll=1\n",
        )

    def test_lts_selection_installs_lts_kernel(self):
        with self._patch(variant="lts"):
            hu.write_firmware_boot("@rootfs", "abcd-02")
        self.assertEqual(self._read("kernel8.img"), "new-lts-kernel")
        self.assertFalse((self.efi / "kernel8.img.new").exists())

    def _stage_update(self):
        with self._patch():
            hu.update_boot_menu("@rootfs", ["@rootfs", "@rootfs-0.6.10"], "uuid", "abcd-02",
                                fallback_subvol="@rootfs-0.6.10")

    def test_update_tries_new_deployment_once_and_keeps_old_as_default(self):
        self._stage_update()
        self.assertEqual(self._read("kernel8.img"), "old-kernel")
        self.assertIn("subvol=@rootfs-0.6.10 ", self._read("cmdline.txt"))
        self.assertEqual(self._read("kernel8-try.img"), "new-kernel")
        self.assertIn("subvol=@rootfs ", self._read("cmdline-try.txt"))
        self.assertEqual((self.tmp / "reboot-param").read_text(), "0 tryboot\n")

    def test_successful_tryboot_becomes_default(self):
        self._stage_update()
        with self._patch():
            hu.confirm_firmware_tryboot("@rootfs", "7.3.3-hippos")
        self.assertEqual(self._read("kernel8.img"), "new-kernel")
        self.assertIn("subvol=@rootfs ", self._read("cmdline.txt"))
        self.assertEqual(sorted(p.name for p in self.efi.iterdir()),
                         ["cmdline.txt", "config.txt", "initramfs8", "kernel8.img"])

    def test_boot_into_old_system_discards_tryboot(self):
        self._stage_update()
        with self._patch():
            hu.confirm_firmware_tryboot("@rootfs-0.6.10", "7.0.12-hippos")
        self.assertEqual(self._read("kernel8.img"), "old-kernel")
        self.assertIn("subvol=@rootfs-0.6.10 ", self._read("cmdline.txt"))
        self.assertFalse((self.efi / "kernel8-try.img").exists())
        self.assertFalse((self.efi / "hippos-tryboot.json").exists())

    def test_kernel_update_leaves_primary_alone(self):
        with self._patch():
            hu.write_firmware_boot("@rootfs-0.6.10", "abcd-02")
            hu.update_boot_menu("@rootfs-0.6.10", [], "uuid", "abcd-02")
        self.assertEqual(self._read("kernel8.img"), "old-kernel")
        self.assertEqual(self._read("kernel8-try.img"), "old-kernel")
