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


def _menuentry(subvol: str) -> str:
    """Build a menuentry block shaped like write_grub_cfg's real output."""
    return (
        f'menuentry "HippOS {subvol}" {{\n'
        f'    insmod btrfs\n'
        f'    linux /{subvol}/boot/vmlinuz root=PARTUUID=xxx rootflags=subvol={subvol}\n'
        f'    initrd /{subvol}/boot/initrd.img\n'
        f'}}\n'
    )


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


class FindMenuentryIndexTests(unittest.TestCase):
    def test_matches_the_correct_block_among_several(self):
        content = "".join(
            _menuentry(s) for s in ("@rootfs-0.6.0", "@rootfs-0.5.1", "@rootfs")
        )
        self.assertEqual(hu.find_menuentry_index(content, "@rootfs-0.6.0"), 0)
        self.assertEqual(hu.find_menuentry_index(content, "@rootfs-0.5.1"), 1)
        self.assertEqual(hu.find_menuentry_index(content, "@rootfs"), 2)

    def test_no_match_falls_back_to_entry_zero(self):
        content = _menuentry("@rootfs-0.6.0")
        self.assertEqual(hu.find_menuentry_index(content, "@rootfs-9.9.9"), 0)

    def test_does_not_confuse_a_subvol_name_that_prefixes_another(self):
        # "@rootfs" must not match the "@rootfs-0.5.1" block it's a prefix of.
        content = _menuentry("@rootfs-0.5.1") + _menuentry("@rootfs")
        self.assertEqual(hu.find_menuentry_index(content, "@rootfs"), 1)


class SetGrubDefaultTests(unittest.TestCase):
    def test_rewrites_default_and_relaxes_zero_timeout(self):
        content = "set default=0\nset timeout=0\nset timeout_style=hidden\n"
        result = hu.set_grub_default(content, 2)
        self.assertIn("set default=2", result)
        self.assertIn("set timeout=5", result)
        self.assertNotIn("set timeout=0", result)
        self.assertIn("set timeout_style=hidden", result)

    def test_leaves_nonzero_timeout_untouched(self):
        content = "set default=0\nset timeout=10\n"
        result = hu.set_grub_default(content, 1)
        self.assertIn("set timeout=10", result)

    def test_does_not_touch_indented_default_lines_inside_boot_counter_block(self):
        # write_grub_cfg's boot-counter block has an indented "set default=1"
        # inside the failed-boot branch; only the top-level line is the
        # active default and should be the one rewritten.
        content = (
            "set default=0\n"
            "if [ \"${boot_counter}\" = \"0\" ] ; then\n"
            "    set default=1\n"
            "fi\n"
        )
        result = hu.set_grub_default(content, 3)
        lines = result.splitlines()
        self.assertEqual(lines[0], "set default=3")
        self.assertEqual(lines[2].strip(), "set default=1")


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
        self.assertFalse(plan.need_new_subvol_cleanup)
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

    def test_retrying_a_failed_apply_cleans_up_the_partial_subvol(self):
        # A previous apply attempt created @rootfs-0.6.0 but didn't finish
        # (e.g. extraction failed). Retrying must delete-then-recreate it,
        # not skip creation because it "already exists".
        plan = hu.plan_apply(
            running="@rootfs-0.5.1", cur_version="0.5.1", remote_version="0.6.0",
            existing_deployments=["@rootfs-0.5.1", "@rootfs-0.6.0"],
        )
        self.assertFalse(plan.need_snapshot)
        self.assertTrue(plan.need_new_subvol_cleanup)

    def test_prunes_the_oldest_deployment_not_the_current_or_new_one(self):
        # Simulates cruft left behind by a previously failed (check=False)
        # prune: three deployments exist where only two should. The correct
        # one to remove is the old rollback slot, not backup_name/new_subvol.
        plan = hu.plan_apply(
            running="@rootfs-0.5.1", cur_version="0.5.1", remote_version="0.5.2",
            existing_deployments=["@rootfs-0.4.0", "@rootfs-0.5.1"],
        )
        self.assertEqual(plan.prune, ["@rootfs-0.4.0"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.5.1", "@rootfs-0.5.2"])
        self.assertNotIn("@rootfs-0.5.1", plan.prune)
        self.assertNotIn("@rootfs-0.5.2", plan.prune)

    def test_pre_prune_order_uses_numeric_not_lexicographic_order(self):
        # Lexicographically, "@rootfs-0.5.2" sorts *after* "@rootfs-0.5.10"
        # and "@rootfs-0.5.11" (comparing the '2' against '1'). If
        # pre_prune_deployments used string order, write_grub_cfg's first
        # (pre-prune) GRUB write — the one made before the boot counter is
        # armed — would put the wrong deployment at the boot-counter's
        # hardcoded fallback slot (menu entry 1).
        plan = hu.plan_apply(
            running="@rootfs-0.5.10", cur_version="0.5.10", remote_version="0.5.11",
            existing_deployments=["@rootfs-0.5.2", "@rootfs-0.5.10"],
        )
        self.assertEqual(
            plan.pre_prune_deployments,
            ["@rootfs-0.5.2", "@rootfs-0.5.10", "@rootfs-0.5.11"],
        )
        self.assertEqual(plan.prune, ["@rootfs-0.5.2"])
        self.assertEqual(plan.final_deployments, ["@rootfs-0.5.10", "@rootfs-0.5.11"])

    def test_pre_prune_deployments_include_the_about_to_be_pruned_entry(self):
        # The first GRUB write happens before pruning runs, so the bootable
        # menu must still list the not-yet-deleted old deployment.
        plan = hu.plan_apply(
            running="@rootfs-0.5.1", cur_version="0.5.1", remote_version="0.5.2",
            existing_deployments=["@rootfs-0.4.0", "@rootfs-0.5.1"],
        )
        self.assertEqual(
            plan.pre_prune_deployments,
            ["@rootfs-0.4.0", "@rootfs-0.5.1", "@rootfs-0.5.2"],
        )


if __name__ == "__main__":
    unittest.main()
