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



def test_native_boards_components_and_api_encoding():
    spec=importlib.util.spec_from_file_location('native_design',ROOT/'tools/ui/build_penpot.py')
    native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
    design=json.loads((ROOT/'tools/ui/design.json').read_text())
    changes,frames,buttons=native.create_shapes(design,native.uid('file'),native.uid('page'))
    assert len(buttons)==19 and len(frames)==5
    assert len([c for c in changes if c['type']=='add-component'])==2
    objects=[c['obj'] for c in changes if c['type']=='add-obj']
    ids={o['id'] for o in objects}
    assert len(ids)==len(objects)
    assert all(o['parent-id'] in ids|{native.ZERO} for o in objects)
    assert any(o.get('interactions') for o in objects)
    assert native.decode_keys({'defaultTeamId':'id'})=={'default-team-id':'id'}
    assert native.export_url({"~#'":'~rhttp://localhost:9001/assets/by-id/abc'}).endswith('/abc')
