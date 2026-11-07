import copy
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('ui_actions',ROOT/'tools/ui/check_actions.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_every_design_action_has_a_real_server_handler():
    assert module.check()==[]


def test_unknown_design_command_fails_contract_check():
    design=json.loads((ROOT/'tools/ui/design.json').read_text())
    design['actions'][0]['payload']['op']='invented_move'
    assert 'no program instruction' in module.check(design)[0]
