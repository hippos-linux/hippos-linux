import importlib.machinery
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / 'overlays' / 'rootfs' / 'usr' / 'lib' / 'hippos' / 'hippos-quickmenu'
sys.path.insert(0, str(SCRIPT_PATH.parent))
DEFAULT_MENU = ROOT / 'overlays' / 'rootfs' / 'usr' / 'share' / 'hippos' / 'quickmenu' / 'quickmenu.xml'


def _load_hippos_quickmenu():
    loader = importlib.machinery.SourceFileLoader('hippos_quickmenu', str(SCRIPT_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[loader.name] = module
    loader.exec_module(module)
    return module


qm = _load_hippos_quickmenu()


class ParseMenuTests(unittest.TestCase):
    def test_default_menu_has_header_and_tabs(self):
        menu = qm.parse_menu(DEFAULT_MENU.read_text())
        self.assertEqual(len(menu.header), 2)
        self.assertEqual(len(menu.footer), 1)
        self.assertEqual([page.title for page in menu.pages], ['Game', 'Gun', 'System', 'Outputs', 'Record'])
        self.assertTrue(menu.pages[0].condition)

    def test_choice_cmd_joins_the_choice_list(self):
        menu = qm.parse_menu('''<features><hgroup display="S"><feature display="Out">
            <choice display="Auto" action="a"/><choice_cmd display="${x}" action="set" action_arg="${y}"/>
        </feature></hgroup></features>''')
        control = menu.pages[0].rows[0].controls[0]
        self.assertEqual(control.kind, 'choices')
        self.assertEqual(len(control.choices), 1)
        self.assertEqual(control.sources[0]['action'], 'set')

    def test_choices_are_collected_into_one_control(self):
        menu = qm.parse_menu('''<features><hgroup display="S"><feature display="Mode">
            <text display="x"/><choice display="A" action="a"/><choice display="B" action="b"/>
        </feature></hgroup></features>''')
        controls = menu.pages[0].rows[0].controls
        self.assertEqual([control.kind for control in controls], ['text', 'choices'])
        self.assertEqual([choice['action'] for choice in controls[1].choices], ['a', 'b'])

    def test_row_condition_is_kept(self):
        menu = qm.parse_menu('<features><hgroup display="S"><feature display="B" if="${x}"/></hgroup></features>')
        self.assertEqual(menu.pages[0].rows[0].condition, '${x}')


class ExpressionTests(unittest.TestCase):
    def test_command_inside_text(self):
        text = 'Now: ${echo "a}b"} today'
        self.assertEqual(qm.expression_command('${df -h | awk \'{print $4}\'}'), "df -h | awk '{print $4}'")
        self.assertEqual(qm.fill_expression('Now: ${date}!', '12:00'), 'Now: 12:00!')
        self.assertIsNone(qm.expression_command('plain'))
        self.assertTrue(qm.expression_command(text))

    def test_is_true(self):
        for value in ('1', 'true', 'on', ' yes\n'):
            self.assertTrue(qm.is_true(value))
        for value in ('', 'off', '0', 'false'):
            self.assertFalse(qm.is_true(value))

    def test_command_choices_pair_labels_and_quoted_values(self):
        source = {'display': '${printf "Speakers\\nHead phones"}', 'action': 'hippos-audio set',
                  'action_arg': "${printf 'alsa.a\\nalsa b'}"}
        self.assertEqual(qm.command_choices(source),
                         [('Speakers', 'hippos-audio set alsa.a'), ('Head phones', "hippos-audio set 'alsa b'")])

    def test_command_choices_without_values_use_labels(self):
        self.assertEqual(qm.command_choices({'display': '${printf "HDMI-1"}', 'action': 'pick'}),
                         [('HDMI-1', 'pick HDMI-1')])

    def test_height_pixels(self):
        self.assertEqual(qm.height_pixels('25%', 1080), 270)
        self.assertEqual(qm.height_pixels('120', 1080), 120)
        self.assertEqual(qm.height_pixels('', 1000), 100)

    def test_run_command_returns_trimmed_output(self):
        self.assertEqual(qm.run_command('echo " hi "'), 'hi')


if __name__ == '__main__':
    unittest.main()
