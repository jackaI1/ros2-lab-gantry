# Experiments around the gantry

I use generated scenes to try inspection and control ideas without a camera, laser scanner or physical robot. None of these experiments drives the gantry. Every number comes from a recorded program run, and GitHub Actions saves the detailed reports, images, point clouds and trained weights as artifacts.

## Install on Linux

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install './experiments[test,vision,cloud,learning]'
export OMP_NUM_THREADS=1
```

The Python modules also run independently of ROS. Open3D is large; I run it on Linux CI instead of installing it on my development Mac. All units in cloud and pose code are metres; inspection guidance is in millimetres and degrees. To reproduce everything in a Linux container, build `docker build -t gantry-experiments experiments` and run with a mounted output folder. No display or GPU is needed.

## Align scans of a room

```sh
python -m gantry_lab.clouds --output output/clouds
```

I generate a small room model with unequal walls, a pillar and shelves, then simulate three overlapping scans with known camera movements, dropout and 2 mm noise. This is synthetic laser-scan-like surface sampling, not a scan of a real building. Voxel downsampling keeps one representative point in each small grid cell. Statistical outlier removal rejects isolated points. FPFH describes the neighbourhood of each point, RANSAC tries feature matches while rejecting bad guesses, and point-to-plane ICP refines the alignment by reducing point-to-surface distances.

`registration.json` contains the fitted transform, fitness (fraction matched), inlier RMSE (root mean squared matched distance), average residual and 95th-percentile residual for every scan pair. A pose graph, a network of relative scan movements, adds a last-to-first loop edge and optimizes the three poses together. Ground truth is used only to score the result. It never initializes registration. `deviation.ply` and `deviation.png` colour the aligned scans by nearest-reference distance, capped at 50 mm in the colour scale. A low nearest-surface distance alone does not prove the correct pose, so tests also check known-transform errors.

## Find a part in depth data

```sh
python -m gantry_lab.depth --output output/depth
```

A CPU ray caster renders axial depth images of a stepped asymmetric part above a bin floor. Camera intrinsics, the focal lengths and image centre, turn each valid pixel into a 3D point. RANSAC removes the dominant floor plane and DBSCAN groups remaining points by their footprint in the bin plane, keeping the measured heights for registration. This links the disconnected top surfaces of a stepped part in an overhead view; touching footprints can merge. Each cluster is registered against the part's visible reference cloud with the same FPFH, RANSAC and ICP pipeline. The reference comes from the same procedural model rather than a downloaded CAD file.

I evaluate clean images, 1 mm noise, 20% missing depth and a contiguous occlusion stripe, with five seeds per condition. `depth.json` reports estimated pose and translation/rotation error for each trial. Success requires under 15 mm and 15 degrees. Candidates are selected by measured fitness and RMSE, not by ground truth. Partial views can remain ambiguous. This is one part in a bin, not a demonstrated multi-part picking system.

## Check flat parts and emit guidance

```sh
python -m gantry_lab.inspection --output output/inspection
```

OpenCV detects inner corners on ten tilted checkerboard images and estimates the camera lens model with `calibrateCamera`. A separate board image at the inspection height establishes the pixel-to-millimetre mapping. The camera and work height must stay fixed. The board has 9 by 6 inner corners with 10 mm spacing.

The generated conveyor images include good parts, oversize parts, missing holes, excessive rotation and absent parts. The inspector measures a rotated bounding rectangle in millimetres and checks the hole's location and area. Its JSON includes pass/fail, each check, dimensions and `guidance: {x_mm, y_mm, angle_deg, frame, valid}`. Offsets are relative to the nominal centre on the checkerboard plane. A failed part has invalid guidance; an absent part has no guidance. This is a file interface a PLC or robot adapter could read, not an implemented Modbus connection. `inspection.json` includes labels, predictions, false-pass and false-fail rates with separate denominators.

## Learn a tracking controller

```sh
python -m gantry_lab.lamp --steps 60000 --seeds 20 --output output/lamp
```

The MuJoCo model is a two-axis pan-tilt lamp arm. It tracks a step target for two seconds and then a moving sinusoidal target. The model has inertia, joint damping, friction, travel limits and bounded motor torque. Gravity is disabled to isolate tracking. One action advances four 5 ms physics steps. The observation includes angles, angular velocities, target error and target velocity; actions are normalized motor torque.

I train PPO, a reinforcement-learning policy that updates from rewarded rollouts, using Stable-Baselines3 and PyTorch. The reward stays between zero and one. Training randomizes body mass and inertia by 0.65 to 1.5 times nominal and friction/damping by 0.5 to 2 times nominal. I tune the proportional and derivative (PD) gains over nine candidates using four separate seeds, then evaluate both controllers over the same 20 new seeds under nominal and randomized physics.

`evaluation.json` records all seeds, gains, requested and actual training steps, per-seed tracking RMSE and settling time, 95% bootstrap confidence intervals, paired error differences, and degradation under changed physics. Settling requires ten consecutive samples below 0.04 rad during the initial step. Trials that do not settle within two seconds are marked unsettled and capped at two seconds; the settled fraction is reported alongside the mean. `tracking.png` compares the measured error over time. A learned controller is not assumed to outperform PD.

## Render parts and learn their full pose

On Linux, install Blender, then run:

```sh
blender --background --threads 2 --python experiments/gantry_lab/render_parts.py -- \
  --output "$PWD/output/rendered" --train 128 --test 64
python -m gantry_lab.pose_learning output/rendered --output output/pose --epochs 80
```

The headless Blender script builds a thin punched plate with a flange and three unequal holes. It renders randomized object pose, metal appearance, lights and clutter using the real Cycles renderer on CPU. Each image has an object mask and an object-to-camera pose: three rotation axes and three translations. The JSON documents camera intrinsics, units and the camera coordinate convention.

The narrow and wide training sets have disjoint seeds and 128 images each. The shared held-out set has 64 images with wider tilt, lighting and occlusion. A small PyTorch convolutional network regresses translation plus a continuous six-value rotation representation. Gram-Schmidt orthogonalization converts it into a proper rotation matrix. Evaluation computes ADD, the average distance between corresponding model points under estimated and true pose. Errors below 20 mm count as successes for this small learning comparison. The report breaks down failure rates by lighting and occlusion and compares both models on identical held-out images. This threshold is not a robot placement tolerance. A small synthetic dataset can yield poor pose accuracy; I preserve failures instead of calling all outputs successful.

## Sources I used

- [Open3D global registration](https://www.open3d.org/docs/release/tutorial/pipelines/global_registration.html) and [multiway registration](https://www.open3d.org/docs/release/tutorial/pipelines/multiway_registration.html) explain the feature, refinement and pose-graph APIs.
- [MuJoCo Python bindings](https://mujoco.readthedocs.io/en/stable/python.html) describe headless physics stepping.
- [Blender render API](https://docs.blender.org/api/current/bpy.ops.render.html) provides the batch rendering call.

## Checks

`pytest experiments/tests` covers known transforms, loop closure, projection, segmentation, calibration, labelled defects, guidance, environment reset, reward bounds, deterministic randomized physics, pose math and dataset validation. CI runs these plus full measurement scripts. It renders 320 images and trains both pose models, and trains PPO for at least 60,000 steps before its 20-seed comparison. Results and honest boundaries are linked from the main README.
