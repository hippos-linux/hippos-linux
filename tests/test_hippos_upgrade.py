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
        names = ["@rootfs-kernel-6.12.1-hippos", "@rootfs-0.6.3", "@rootfs-0.6.2"]
        self.assertEqual(
            hu.sort_deployment_names(names),
            ["@rootfs-0.6.2", "@rootfs-0.6.3", "@rootfs-kernel-6.12.1-hippos"],
        )


class ParseDeploymentNamesTests(unittest.TestCase):
    def test_filters_to_rootfs_prefixed_names_and_sorts_numerically(self):
        output = _subvol_list_output(["@userdata", "@rootfs-0.5.10", "@rootfs-0.5.2", "@overlay"])
        self.assertEqual(
            hu.parse_deployment_names(output),
            ["@rootfs-0.5.2", "@rootfs-0.5.10"],
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
    """These assert the actual snapshot/create/prune *decisions* — the
    externally meaningful behaviour of cmd_apply — not that some mock got
    called."""

    def test_first_update_from_bare_rootfs_snapshots_it(self):
        plan = hu.plan_apply(
            running="@rootfs", cur_version="0.1.0", remote_version="0.2.0",
            existing_deployments=[],
        )
        self.assertEqual(plan.backup_name, "@rootfs-0.1.0")
        self.assertTrue(plan.need_snapshot)
        self.assertEqual(plan.new_subvol, "@rootfs-0.2.0")
        self.assertEqual(plan.prune, [])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.1.0", "@rootfs-0.2.0"])

    def test_steady_state_update_does_not_resnapshot_the_running_subvol(self):
        # Post-first-update, running == f"@rootfs-{cur}" already — there is
        # nothing to snapshot, since the running subvolume already occupies
        # its own permanent slot (root is a read-only overlay lowerdir).
        plan = hu.plan_apply(
            running="@rootfs-0.5.1", cur_version="0.5.1", remote_version="0.5.2",
            existing_deployments=["@rootfs-0.5.1"],
        )
        self.assertFalse(plan.need_snapshot)
        self.assertEqual(plan.prune, [])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.5.1", "@rootfs-0.5.2"])

    def test_retrying_a_failed_apply_prunes_the_partial_subvol(self):
        # A previous apply attempt created @rootfs-0.6.0 but didn't finish
        # (e.g. extraction failed). Retrying must delete-then-recreate it,
        # not skip creation because it "already exists".
        plan = hu.plan_apply(
            running="@rootfs-0.5.1", cur_version="0.5.1", remote_version="0.6.0",
            existing_deployments=["@rootfs-0.5.1", "@rootfs-0.6.0"],
        )
        self.assertFalse(plan.need_snapshot)
        self.assertEqual(plan.prune, ["@rootfs-0.6.0"])
        self.assertEqual(plan.retained_deployments, ["@rootfs-0.5.1"])

    def test_prunes_the_oldest_deployment_not_the_current_or_new_one(self):
        plan = hu.plan_apply(
            running="@rootfs-0.5.1", cur_version="0.5.1", remote_version="0.5.2",
            existing_deployments=["@rootfs-0.4.0", "@rootfs-0.5.1"],
        )
        self.assertEqual(plan.prune, ["@rootfs-0.4.0"])
        self.assertEqual(plan.retained_deployments, ["@rootfs-0.5.1"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.5.1", "@rootfs-0.5.2"])

    def test_prune_order_uses_numeric_not_lexicographic_order(self):
        # Lexicographically, "@rootfs-0.5.2" sorts *after* "@rootfs-0.5.10"
        # and "@rootfs-0.5.11"; write_grub_cfg relies on version order to put
        # the right deployment at the boot counter's fallback slot.
        plan = hu.plan_apply(
            running="@rootfs-0.5.10", cur_version="0.5.10", remote_version="0.5.11",
            existing_deployments=["@rootfs-0.5.2", "@rootfs-0.5.9", "@rootfs-0.5.10"],
        )
        self.assertEqual(plan.prune, ["@rootfs-0.5.2", "@rootfs-0.5.9"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.5.10", "@rootfs-0.5.11"])

    def test_prunes_bare_rootfs_left_behind_by_the_first_update(self):
        # Fresh 0.6.1 install updated to 0.6.2 leaves @rootfs, its snapshot
        # @rootfs-0.6.1, and the running @rootfs-0.6.2.
        plan = hu.plan_apply(
            running="@rootfs-0.6.2", cur_version="0.6.2", remote_version="0.6.3",
            existing_deployments=["@rootfs-0.6.1", "@rootfs-0.6.2"],
            bare_rootfs_exists=True,
        )
        self.assertEqual(plan.prune, ["@rootfs", "@rootfs-0.6.1"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.6.2", "@rootfs-0.6.3"])

    def test_os_update_prunes_kernel_snapshots(self):
        plan = hu.plan_apply(
            running="@rootfs-0.6.2", cur_version="0.6.2", remote_version="0.6.3",
            existing_deployments=["@rootfs-0.6.2", "@rootfs-kernel-6.12.1-hippos"],
        )
        self.assertEqual(plan.prune, ["@rootfs-kernel-6.12.1-hippos"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.6.2", "@rootfs-0.6.3"])

    def test_never_prunes_bare_rootfs_while_it_is_running(self):
        plan = hu.plan_apply(
            running="@rootfs", cur_version="0.6.1", remote_version="0.6.2",
            existing_deployments=[], bare_rootfs_exists=True,
        )
        self.assertEqual(plan.prune, [])
        self.assertTrue(plan.need_snapshot)

if __name__ == "__main__":
    unittest.main()
