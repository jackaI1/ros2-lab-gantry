"""Run with Blender --background --python ... -- --output DIR (Linux CI)."""
import argparse
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector
import numpy as np


def box(name, location, scale):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj=bpy.context.object;obj.name=name;obj.dimensions=scale
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    return obj


def part():
    plate=box('stamped plate',(0,0,0),(.12,.08,.003))
    for x,y,r in [(-.035,-.02,.007),(.03,.018,.010),(.035,-.02,.004)]:
        bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=r,depth=.02,location=(x,y,0))
        tool=bpy.context.object
        bpy.context.view_layer.objects.active=plate
        mod=plate.modifiers.new('punched hole','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='FAST';mod.object=tool
        bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(tool,do_unlink=True)
    flange=box('bent flange',(-.0585,0,.012),(.003,.08,.025))
    plate.select_set(True);flange.select_set(True)
    bpy.context.view_layer.objects.active=plate;bpy.ops.object.join()
    bevel=plate.modifiers.new('soft cut edge','BEVEL');bevel.width=.0007;bevel.segments=2
    plate.pass_index=1
    return plate


def render_dataset(output,train=512,test=128):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8
    scene.render.resolution_x=96;scene.render.resolution_y=96;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.film_transparent=False
    scene.world.use_nodes=True
    background=scene.world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value=(.08,.08,.08,1)
    background.inputs['Strength'].default_value=.3
    scene.view_settings.view_transform='Standard'
    bpy.ops.object.camera_add(location=(0,0,.65));camera=bpy.context.object
    camera.rotation_euler=(0,0,0);camera.data.type='PERSP';camera.data.lens=65;camera.data.sensor_width=36
    scene.camera=camera
    board=box('work surface',(0,0,-.045),(1,1,.01))
    floor_material=bpy.data.materials.new('matte work surface');floor_material.diffuse_color=(.06,.1,.15,1)
    board.data.materials.append(floor_material)
    material=bpy.data.materials.new('steel');material.use_nodes=True
    steel=material.node_tree.nodes.get('Principled BSDF')
    object_part=part();object_part.data.materials.append(material)
    bpy.ops.object.light_add(type='AREA',location=(.1,-.1,.4));light=bpy.context.object;light.data.shape='DISK';light.data.size=.3
    clutter=[box('clutter',(.2,0,.03),(.025,.025,.015)) for _ in range(2)]
    for item in clutter:item.pass_index=2
    scene.view_layers[0].use_pass_object_index=True
    scene.use_nodes=True;nodes=scene.node_tree.nodes;nodes.clear()
    layers=nodes.new('CompositorNodeRLayers')
    composite=nodes.new('CompositorNodeComposite');scene.node_tree.links.new(layers.outputs['Image'],composite.inputs[0])
    mask=nodes.new('CompositorNodeIDMask');mask.index=1;mask.use_antialiasing=True
    scene.node_tree.links.new(layers.outputs['IndexOB'],mask.inputs[0])
    save=nodes.new('CompositorNodeOutputFile');save.format.file_format='PNG';save.format.color_mode='BW'
    scene.node_tree.links.new(mask.outputs[0],save.inputs[0])
    # Camera looks down local -Z; convert to computer-vision camera +Z, +Y down.
    convention=Matrix.Diagonal((1,-1,-1,1))
    records=[]
    for split,count,offset in [('narrow',train,10000),('wide',train,20000),('heldout',test,30000)]:
        folder=output/split;folder.mkdir(exist_ok=True)
        for i in range(count):
            seed=offset+i;rng=np.random.default_rng(seed)
            wide=split!='narrow'
            bound=.55 if wide else .12
            object_part.location=(float(rng.uniform(-.025,.025)),float(rng.uniform(-.025,.025)),float(rng.uniform(-.008,.008)))
            object_part.rotation_euler=(float(rng.uniform(-bound,bound)),float(rng.uniform(-bound,bound)),float(rng.uniform(-math.pi,math.pi)))
            lighting='dark' if i%2==0 else 'bright'
            light.data.energy=float(rng.uniform(.15,.6) if wide and lighting=='dark' else rng.uniform(2.5,9) if wide else 3)
            light.location=(float(rng.uniform(-.25,.25)) if wide else .1,-.1,.4)
            steel.inputs['Base Color'].default_value=(*([float(rng.uniform(.15,.7))]*3),1)
            steel.inputs['Metallic'].default_value=float(rng.uniform(.2,.95) if wide else .7)
            steel.inputs['Roughness'].default_value=float(rng.uniform(.15,.75) if wide else .3)
            occlusion='high' if wide and i%3==0 else 'none'
            for j,item in enumerate(clutter):
                item.location=(float(object_part.location.x+(-.02+j*.04)) if occlusion=='high' else .2+j*.05,
                               float(object_part.location.y),.055)
                item.rotation_euler.z=float(rng.uniform(0,math.pi))
            scene.cycles.seed=seed
            bpy.context.view_layer.update()
            cv_pose=convention@camera.matrix_world.inverted()@object_part.matrix_world
            image=f'{i:04d}.png';mask_name=f'{i:04d}-mask.png'
            scene.render.filepath=str(folder/image)
            save.base_path=str(folder);save.file_slots[0].path=f'{i:04d}-mask-'
            bpy.ops.render.render(write_still=True)
            if i == 0:
                check=bpy.data.images.load(str(folder/image),check_existing=False)
                pixels=np.array(check.pixels[:]).reshape(-1,4)[:,:3]
                bpy.data.images.remove(check)
                if pixels.mean(axis=1).std() < (.015 if split=='narrow' else .0002):
                    raise RuntimeError('Rendered RGB lacks visible geometry; check lights and colour configuration')
            generated=folder/f'{i:04d}-mask-0001.png'
            generated.rename(folder/mask_name)
            # Reference coordinates use object local mesh vertices, including the flange.
            records.append({'split':split,'seed':seed,'image':f'{split}/{image}','mask':f'{split}/{mask_name}',
                'rotation':[list(row)[:3] for row in list(cv_pose)[:3]],
                'translation_m':list(cv_pose.translation),'lighting':lighting if wide else 'nominal',
                'occlusion':occlusion})
    result={'version':1,'generator':'Blender Cycles CPU, stamped plate with three punched holes and flange',
            'intrinsics':[[65/36*96,0,48],[0,65/36*96,48],[0,0,1]],
            'camera_convention':'X right, Y down, Z forward; object-to-camera; metres',
            'model_points_m':[list(v.co) for v in object_part.data.vertices],
            'records':records}
    (output/'dataset.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--train',type=int,default=512);parser.add_argument('--test',type=int,default=128)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    render_dataset(args.output,args.train,args.test)
