"""FPFH/RANSAC initialization, point-to-plane ICP and loop-closure optimization."""
import copy
import json
from pathlib import Path
import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation

REG = o3d.pipelines.registration


def cloud(points):
    result = o3d.geometry.PointCloud()
    result.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=float))
    return result


def transform(xyz, matrix):
    return np.asarray(xyz) @ matrix[:3,:3].T + matrix[:3,3]


def pose(xyz=(0,0,0), angles=(0,0,0)):
    result = np.eye(4)
    result[:3,:3] = Rotation.from_euler('xyz', angles).as_matrix()
    result[:3,3] = xyz
    return result


def prepare(points, voxel):
    result = points.voxel_down_sample(voxel)
    result, _ = result.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.5)
    result.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel*3, max_nn=40))
    # Centroid-facing normals give each scan a consistent descriptor convention.
    result.orient_normals_towards_camera_location(result.get_center())
    features = REG.compute_fpfh_feature(result,
        o3d.geometry.KDTreeSearchParamHybrid(radius=voxel*6, max_nn=100))
    return result, features


def register(source, target, voxel=.04, seed=7):
    o3d.utility.random.seed(seed)
    src, sf = prepare(source, voxel)
    dst, tf = prepare(target, voxel)
    if min(len(src.points), len(dst.points)) < 20:
        raise ValueError('Registration needs at least 20 downsampled points')
    initial = REG.registration_ransac_based_on_feature_matching(
        src, dst, sf, tf, True, voxel*2,
        REG.TransformationEstimationPointToPoint(False), 3,
        [REG.CorrespondenceCheckerBasedOnEdgeLength(.9),
         REG.CorrespondenceCheckerBasedOnDistance(voxel*2)],
        REG.RANSACConvergenceCriteria(60000, .999))
    refined = REG.registration_icp(src, dst, voxel*1.5, initial.transformation,
        REG.TransformationEstimationPointToPlane(), REG.ICPConvergenceCriteria(max_iteration=80))
    moved = copy.deepcopy(source).transform(refined.transformation)
    residual = np.asarray(moved.compute_point_cloud_distance(target))
    metrics = {'fitness': float(refined.fitness), 'inlier_rmse_m': float(refined.inlier_rmse),
               'residual_mean_m': float(residual.mean()), 'residual_p95_m': float(np.quantile(residual,.95)),
               'ransac_fitness': float(initial.fitness), 'points_used': [len(src.points),len(dst.points)]}
    return refined.transformation, metrics


def pose_error(estimate, truth):
    delta = np.linalg.inv(truth) @ estimate
    return {'translation_m': float(np.linalg.norm(delta[:3,3])),
            'rotation_deg': float(np.degrees(Rotation.from_matrix(delta[:3,:3]).magnitude()))}


def room(seed=4, count=6000):
    """Synthetic interior: floor, unequal walls, off-centre shelves and a pillar."""
    rng = np.random.default_rng(seed)
    # Sample the faces of unequal boxes so the interior has no rotational symmetry.
    boxes = [((0,0,0),(4,3,.04)), ((0,0,0),(.04,3,2.4)),
             ((0,0,0),(4,.04,2.4)), ((.8,.7,0),(.25,.33,1.4)),
             ((2.1,.2,.6),(1,.6,.13)), ((2.7,1.9,0),(.5,.7,.8))]
    points=[]
    for origin, size in boxes:
        xyz=rng.random((count//len(boxes),3))*size
        face=rng.integers(0,3,len(xyz))
        side=rng.integers(0,2,len(xyz))
        xyz[np.arange(len(xyz)),face] = np.array(size)[face]*side
        points.append(xyz+origin)
    return np.vstack(points)


def multiway(scans, voxel=.04):
    graph = REG.PoseGraph()
    graph.nodes.append(REG.PoseGraphNode(np.eye(4)))
    odometry=np.eye(4)
    pairs=[]
    for i in range(len(scans)):
        for j in range(i+1,len(scans)):
            matrix, metrics = register(scans[i], scans[j], voxel, seed=7+i*10+j)
            if metrics['fitness'] < .25:
                raise ValueError(f'Insufficient overlap for pair {i},{j}')
            information=REG.get_information_matrix_from_point_clouds(scans[i], scans[j], voxel*2,matrix)
            if j == i+1:
                odometry=matrix@odometry
                graph.nodes.append(REG.PoseGraphNode(np.linalg.inv(odometry)))
            graph.edges.append(REG.PoseGraphEdge(i,j,matrix,information,uncertain=j!=i+1))
            pairs.append(dict(source=i,target=j,loop_closure=j!=i+1,transform=matrix.tolist(),**metrics))
    REG.global_optimization(graph,REG.GlobalOptimizationLevenbergMarquardt(),
        REG.GlobalOptimizationConvergenceCriteria(),
        REG.GlobalOptimizationOption(max_correspondence_distance=voxel*2,
                                     edge_prune_threshold=.25,reference_node=0))
    return [np.asarray(n.pose) for n in graph.nodes], pairs


def heatmap(points, reference, path):
    distances=np.asarray(points.compute_point_cloud_distance(reference))
    from matplotlib import colormaps
    points.colors=o3d.utility.Vector3dVector(colormaps['turbo'](np.clip(distances/.05,0,1))[:,:3])
    o3d.io.write_point_cloud(str(path), points)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    xyz=np.asarray(points.points)
    fig,ax=plt.subplots(figsize=(7,4))
    image=ax.scatter(xyz[:,0],xyz[:,1],c=distances,s=2,cmap='turbo',vmin=0,vmax=.05)
    ax.set(xlabel='X (m)',ylabel='Y (m)',title='Deviation from reference, top view')
    fig.colorbar(image,ax=ax,label='Nearest reference distance (m)')
    fig.tight_layout();fig.savefig(Path(path).with_suffix('.png'));plt.close(fig)
    return {'mean_m':float(distances.mean()),'p95_m':float(np.quantile(distances,.95))}


def demo(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rng=np.random.default_rng(13)
    reference=room()
    truth=[np.eye(4),pose((.16,-.10,.07),(.04,-.05,.16)),pose((-.10,.08,.03),(-.03,.04,-.12))]
    scans=[]
    for i,matrix in enumerate(truth):
        # Each view has an independent 15% dropout and 2 mm measurement noise.
        keep=rng.random(len(reference))>.15
        xyz=transform(reference[keep],np.linalg.inv(matrix))+rng.normal(0,.002,(sum(keep),3))
        scans.append(cloud(xyz))
        o3d.io.write_point_cloud(str(output/f'scan-{i}.ply'),scans[-1])
    poses,pairs=multiway(scans)
    merged=o3d.geometry.PointCloud()
    for scan,matrix in zip(scans,poses):
        merged+=copy.deepcopy(scan).transform(matrix)
    result={'dataset':'seeded synthetic interior, metres; not a real laser survey',
            'seed':13,'pairs':pairs,'poses':[p.tolist() for p in poses],
            'pose_errors':[pose_error(p,t) for p,t in zip(poses,truth)],
            'deviation':heatmap(merged,cloud(reference),output/'deviation.ply')}
    (output/'registration.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='output/clouds')
    print(json.dumps(demo(parser.parse_args().output),indent=2))
