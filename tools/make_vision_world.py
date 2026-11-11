"""Write src/gantry_description/worlds/lab_vision.sdf from the same plate geometry the detector uses."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vision'))
from gantry_vision.plate import PLATE_CENTRE, CENTRE_Z, WELL_NAMES, nominal_wells  # noqa: E402

BASE = (ROOT / 'src/gantry_description/worlds/lab.sdf').read_text()


def build():
    wells = []
    for name, (x, y) in zip(WELL_NAMES, nominal_wells()):
        local_x, local_y = x - PLATE_CENTRE[0], y - PLATE_CENTRE[1]
        wells.append(f'<visual name="well_{name}"><pose>{local_x:.4f} {local_y:.4f} 0.0105 0 0 0</pose>'
                     '<geometry><cylinder><radius>0.003</radius><length>0.001</length></cylinder></geometry>'
                     '<material><diffuse>0.12 0.12 0.12 1</diffuse></material></visual>')
    plate = (f'<model name="plate"><static>true</static><pose>{PLATE_CENTRE[0]} {PLATE_CENTRE[1]} {CENTRE_Z} 0 0 0</pose>'
             '<link name="plate"><visual name="body"><geometry><box><size>0.128 0.086 0.02</size></box></geometry>'
             '<material><diffuse>0.15 0.4 0.7 1</diffuse></material></visual>' + ''.join(wells) +
             '</link></model>')
    camera = ('<model name="overhead_camera"><static>true</static>'
              f'<pose>{PLATE_CENTRE[0]} {PLATE_CENTRE[1]} 0.35 0 1.5707963 0</pose>'
              '<link name="lens"><sensor name="overhead" type="camera"><always_on>1</always_on>'
              '<update_rate>5</update_rate><topic>overhead/image</topic><camera>'
              '<horizontal_fov>1.0471976</horizontal_fov><image><width>320</width><height>240</height></image>'
              '<clip><near>0.05</near><far>5</far></clip></camera></sensor></link></model>')
    text = BASE
    start = text.index('<model name="plate">')
    end = text.index('</model>', start) + len('</model>')
    text = text[:start] + plate + text[end:]
    text = text.replace('<plugin filename="gz-sim-scene-broadcaster-system"',
                        '<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">'
                        '<render_engine>ogre2</render_engine></plugin>\n'
                        '<plugin filename="gz-sim-scene-broadcaster-system"', 1)
    text = text.replace('<!-- Fixed tool stand.', '<!-- Overhead camera: same pose and lens as vision/gantry_vision/camera.py reads. -->\n'
                        + camera + '\n<!-- Fixed tool stand.', 1)
    return '<?xml version="1.0"?>\n' + text.split('\n', 1)[1] if text.startswith('<?xml') else text


if __name__ == '__main__':
    (ROOT / 'src/gantry_description/worlds/lab_vision.sdf').write_text(build())
