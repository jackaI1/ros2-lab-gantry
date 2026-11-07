import numpy as np
from gantry_lab.clouds import pose
from gantry_lab.depth import project, render, segment


def test_projection_millimetre_pixel_geometry():
    intrinsic=np.array([[100.,0,1],[0,100.,1],[0,0,1]])
    depth=np.zeros((3,3));depth[1,1]=2.;depth[1,2]=2.
    points=project(depth,intrinsic)
    np.testing.assert_allclose(points,[[0,0,2],[.02,0,2]])
    assert len(project(np.array([[np.nan,0.]])))==0


def test_render_plane_removal_and_cluster_use_measured_depth():
    image=render(pose((.01,0,.92)),seed=9,noise=.0005,missing=.05)
    clusters,plane=segment(image)
    assert abs(plane[2])>.99
    assert len(clusters)==1
    points=np.asarray(clusters[0].points)
    assert .85<points[:,2].mean()<.93
    assert .09<np.ptp(points[:,0])<.15
    np.testing.assert_array_equal(image,render(pose((.01,0,.92)),seed=9,noise=.0005,missing=.05))
