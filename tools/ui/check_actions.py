"""Validate design commands against actual server dispatch and program validation."""
import ast
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/gantry_control'))
from gantry_control.pendant import Pendant


def checked_operations(path, variable):
    tree=ast.parse(path.read_text())
    operations=set()
    for node in ast.walk(tree):
        if isinstance(node,ast.Compare) and isinstance(node.left,ast.Name) and node.left.id==variable:
            for comparator in node.comparators:
                for item in ast.walk(comparator):
                    if isinstance(item,ast.Constant) and isinstance(item.value,str):
                        operations.add(item.value)
    return operations


def check(design=None):
    design=design or json.loads((ROOT/'tools/ui/design.json').read_text())
    server=(ROOT/'src/gantry_control/gantry_control/server.py').read_text()
    commands=checked_operations(ROOT/'src/gantry_control/gantry_control/server.py','op')
    program_ops=checked_operations(ROOT/'src/gantry_control/gantry_control/pendant.py','op')
    errors=[]
    for action in design['actions']:
        if action['screen'] not in design['screens']:
            errors.append(action['name']+': missing screen')
        kind=action['kind'];payload=action.get('payload',{})
        if kind=='command' and payload.get('op') not in commands:
            errors.append(action['name']+': no server command')
        elif kind=='program':
            if payload.get('op') not in program_ops:
                errors.append(action['name']+': no program instruction')
            else:
                pendant=Pendant();pendant.record('approach',(.04,.04,.01),'joint',[0,0,0])
                try:pendant.prepare([payload],(.04,.04,.01),0)
                except ValueError as exc:errors.append(action['name']+': '+str(exc))
        elif kind=='service':
            endpoint=action['endpoint']
            valid=(endpoint in server or endpoint.removeprefix('/gantry/') in ('emergency_stop','limit_switch')
                   and "'/gantry/' + name" in server)
            if not valid:errors.append(action['name']+': no service endpoint')
        elif kind=='cancel' and action['endpoint'] not in server:
            errors.append(action['name']+': no cancellable action')
    return errors


if __name__=='__main__':
    errors=check();print('\n'.join(errors) if errors else 'All 14 design actions map to the working server')
    raise SystemExit(bool(errors))
