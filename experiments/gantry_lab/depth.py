"""CPU ray-cast depth, bin-plane removal, clustering and model registration."""
import json
from pathlib import Path
import numpy as np
import open3d as o3d
from gantry_lab.clouds import cloud, pose, register, pose_error

INTRINSICS = np.array([[420.,0,160.],[0,420.,120.],[0,0,1.]])


def project(depth, intrinsic=INTRINSICS):
    depth=np.asarray(depth,dtype=float)
    if depth.ndim!=2 or intrinsic.shape!=(3,3) or intrinsic[0,0]<=0 or intrinsic[1,1]<=0:
        raise ValueError('Expected depth image and positive focal lengths')
    v,u=np.indices(depth.shape)
    valid=np.isfinite(depth)&(depth>0)
    z=depth[valid]
    return np.column_stack(((u[valid]-intrinsic[0,2])*z/intrinsic[0,0],
                            (v[valid]-intrinsic[1,2])*z/intrinsic[1,1], z))


def part_mesh():
    mesh=o3d.geometry.TriangleMesh.create_box(.12,.075,.025).translate((-.06,-.0375,-.025))
    mesh+=o3d.geometry.TriangleMesh.create_box(.033,.042,.035).translate((-.055,-.032,-.06))
    mesh+=o3d.geometry.TriangleMesh.create_box(.02,.025,.015).translate((.04,.012,-.04))
    mesh.compute_vertex_normals()
    return mesh


def render(matrix, seed=0, noise=0., missing=0., occlusion=0., include_plane=True):
    scene=o3d.t.geometry.RaycastingScene()
    mesh=part_mesh().transform(matrix)
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    if include_plane:
        floor=o3d.geometry.TriangleMesh.create_box(1,1,.01).translate((-.5,-.5,1.))
        scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(floor))
    # Unnormalised z=1 ray directions yield axial depth, matching pinhole projection.
    v,u=np.indices((240,320));rays=np.zeros((240,320,6),np.float32)
    rays[:,:,3]=(u-160)/420;rays[:,:,4]=(v-120)/420;rays[:,:,5]=1
    depth=scene.cast_rays(o3d.core.Tensor(rays))['t_hit'].numpy()
    depth[~np.isfinite(depth)]=0
    rng=np.random.default_rng(seed)
    valid=depth>0
    depth[valid]+=rng.normal(0,noise,sum(valid.ravel()))
    depth[rng.random(depth.shape)<missing]=0
    if occlusion:
        # A contiguous missing stripe hides part of the work area.
        depth[:,int(160-80*occlusion):160]=0
    return depth


def segment(depth, seed=4):
    o3d.utility.random.seed(seed)
    points=cloud(project(depth)).voxel_down_sample(.002)
    if len(points.points)<30:
        return [],None
    plane,indices=points.segment_plane(distance_threshold=.004,ransac_n=3,num_iterations=500)
    if abs(plane[2])<.9:
        raise ValueError('Dominant plane is not the expected bin floor')
    objects=points.select_by_index(indices,invert=True)
    # Group in the bin plane: stepped top surfaces are disconnected in Z in
    # a single overhead view, but belong to one contiguous part footprint.
    xyz=np.asarray(objects.points)
    footprint=cloud(np.column_stack((xyz[:,:2],np.zeros(len(xyz)))))
    labels=np.asarray(footprint.cluster_dbscan(eps=.009,min_points=12))
    clusters=[objects.select_by_index(np.flatnonzero(labels==label)) for label in sorted(set(labels)-{-1})]
    return clusters,plane


def demo(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    model_depth=render(pose((0,0,.92)),include_plane=False)
    model=cloud(project(model_depth)-[0,0,.92])
    o3d.io.write_point_cloud(str(output/'visible-model.ply'),model)
    cases=[]
    settings=[('clean',0.,0.,0.),('noise',.001,0.,0.),('missing',.001,.20,0.),('occluded',.001,.1,.35)]
    for label,noise,missing,occlusion in settings:
        trials=[]
        for seed in range(5):
            truth=pose((.015+seed*.002,-.012,.92),(0,0,.14+seed*.03))
            depth=render(truth,seed,noise,missing,occlusion)
            clusters,plane=segment(depth)
            found=[]
            for candidate in clusters:
                if len(candidate.points)<50:
                    continue
                estimate,metrics=register(model,candidate,voxel=.004,seed=seed)
                errors=pose_error(estimate,truth)
                found.append(dict(**metrics,**errors,estimate=estimate.tolist()))
            # Select by observed registration quality, never ground-truth error.
            found.sort(key=lambda x:(-x['fitness'],x['inlier_rmse_m']))
            best=found[0] if found else None
            success=bool(best and best['translation_m']<.015 and best['rotation_deg']<15)
            trials.append({'seed':seed,'clusters':len(clusters),'success':success,'best':best})
            if seed==0:
                np.save(output/f'{label}-depth.npy',depth)
                o3d.io.write_point_cloud(str(output/f'{label}-observed.ply'),cloud(project(depth)))
        cases.append({'condition':label,'noise_sd_m':noise,'missing_fraction':missing,
                      'occlusion_stripe':occlusion,'success_rate':sum(t['success'] for t in trials)/len(trials),
                      'trials':trials})
    result={'dataset':'seeded rendered axial depth of asymmetric stepped part above bin floor',
            'intrinsics':INTRINSICS.tolist(),'success_translation_m':.015,'success_rotation_deg':15,
            'cases':cases}
    (output/'depth.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='output/depth')
    print(json.dumps(demo(parser.parse_args().output),indent=2))
