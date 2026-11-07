import numpy as np
import pytest
from gantry_lab.clouds import cloud, room, transform, pose, register, pose_error, multiway


def test_known_transform_fpfh_and_icp():
    xyz=room(count=4200)
    truth=pose((.12,-.08,.04),(.04,-.03,.2))
    rng=np.random.default_rng(12)
    source=cloud(transform(xyz,np.linalg.inv(truth))+rng.normal(0,.001,xyz.shape))
    estimate,metrics=register(source,cloud(xyz),.045)
    errors=pose_error(estimate,truth)
    assert errors['translation_m']<.012
    assert errors['rotation_deg']<1.5
    assert metrics['fitness']>.9 and metrics['inlier_rmse_m']<.025
    assert metrics['residual_p95_m']<.015


def test_loop_closure_recovers_three_scan_poses():
    xyz=room(count=3600)
    truth=[np.eye(4),pose((.1,0,.03),(0,.04,.12)),pose((0,-.12,0),(.02,0,-.1))]
    scans=[cloud(transform(xyz,np.linalg.inv(t))) for t in truth]
    estimates,pairs=multiway(scans,.05)
    assert len(pairs)==3 and sum(p['loop_closure'] for p in pairs)==1
    for estimate,target in zip(estimates,truth):
        assert pose_error(estimate,target)['translation_m']<.02
        assert pose_error(estimate,target)['rotation_deg']<2


def test_insufficient_cloud_is_rejected():
    with pytest.raises(ValueError):
        register(cloud([[0,0,0],[1,0,0]]),cloud([[0,0,0],[1,0,0]]))
