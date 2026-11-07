"""Read a committed real Gazebo fault recording without ROS or extra packages."""
import argparse
import json
from pathlib import Path
import sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src/gantry_control'))
from gantry_control.triage import report

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fault',choices=['emergency_stop','limit_switch'],default='emergency_stop')
args=parser.parse_args()
folder=root/'docs/results/runs'/args.fault
record=json.loads((folder/'replay.json').read_text())
print(report(folder/record['original_manifest']))
