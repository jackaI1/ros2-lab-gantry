import importlib.util
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('playbooks',ROOT/'tools/check_playbooks.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_playbooks_match_controller_and_fault_contract():
    assert module.check()==[]


def test_controller_or_signature_change_requires_page_review(tmp_path,monkeypatch):
    for source in module.SOURCES:
        destination=tmp_path/source;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/source,destination)
    shutil.copytree(ROOT/'docs/playbook',tmp_path/'docs/playbook')
    assert module.check(tmp_path)==[]
    controller=tmp_path/'src/gantry_description/config/controllers.yaml'
    controller.write_text(controller.read_text().replace('update_rate: 100','update_rate: 90'))
    assert all('contract changed' in error for error in module.check(tmp_path))
    shutil.copyfile(ROOT/'src/gantry_description/config/controllers.yaml',controller)
    monkeypatch.setitem(module.SIGNATURES,'new motor fault','new_fault')
    errors=module.check(tmp_path)
    assert any('new_fault: missing playbook' in error for error in errors)
