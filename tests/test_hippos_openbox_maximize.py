import importlib.machinery
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos' / 'hippos-openbox-maximize'
loader = importlib.machinery.SourceFileLoader('hippos_openbox_maximize', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
tool = importlib.util.module_from_spec(spec)
loader.exec_module(tool)

CONFIG = '<openbox_config>\n<applications>\n<!-- examples -->\n</applications>\n</openbox_config>\n'


class OpenboxMaximizeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Path(tmp.name) / 'openbox'
        self.config.mkdir()
        for name in tool.CONFIG_NAMES:
            (self.config / name).write_text(CONFIG)

    def run_tool(self, state):
        with mock.patch.dict(os.environ, {'XDG_CONFIG_HOME': str(self.config.parent)}):
            return tool.main([state])

    def test_on_adds_the_rule_once_and_off_removes_it(self):
        self.run_tool('on')
        self.run_tool('on')
        for name in tool.CONFIG_NAMES:
            text = (self.config / name).read_text()
            self.assertEqual(text.count(tool.RULE), 1)
            self.assertLess(text.index(tool.RULE), text.index(tool.END))
        self.run_tool('off')
        for name in tool.CONFIG_NAMES:
            self.assertEqual((self.config / name).read_text(), CONFIG)

    def test_rejects_other_arguments(self):
        with mock.patch('sys.stderr'):
            self.assertEqual(tool.main(['maybe']), 2)


if __name__ == '__main__':
    unittest.main()
