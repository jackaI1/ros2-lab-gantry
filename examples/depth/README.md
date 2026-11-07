# One recorded synthetic depth image

`seed0.npz` contains `depth_m` (240 by 320 axial depth values in metres) and `intrinsics` (the camera calibration matrix). Zero means no return. It was ray-cast by the real Open3D CPU renderer in [this CI run](https://github.com/jackaI1/ros2-lab-gantry/actions/runs/42325322425), using `gantry_lab.depth.render`, seed 0, no noise or dropout. The part's model-to-camera translation is (0.015, -0.012, 0.92) metres, with a 0.14 radian rotation about Z. The floor is at Z = 1 metre.

After installing the cloud dependencies:

```sh
python -m gantry_lab.depth --depth examples/depth/seed0.npz --output output/depth-file
```

This command processes the depth measurements without using the known pose. The ground truth above is only for scoring. The file is compressed to keep the repository small.
