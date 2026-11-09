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
