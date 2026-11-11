"""Train on fresh rendered scenes, score held-out scenes, and export ONNX.

python -m gantry_vision.train --output artifacts/vision --epochs 20
"""
import argparse
import json
from pathlib import Path

import numpy as np

from gantry_vision.camera import load_camera
from gantry_vision.dataset import make_set
from gantry_vision.inference import DEFAULT_MIN_CONFIDENCE, decode, preprocess
from gantry_vision.plate import wells_at

HELD_OUT_SEED = 987_654
HELD_OUT_SPREAD = 1.4          # held-out plates move and tilt beyond the training range


def _images(samples):
    return np.stack([preprocess(s.image)[0] for s in samples])


def _train_batch(samples):
    import torch
    x = torch.from_numpy(_images(samples))
    y = torch.from_numpy(np.stack([s.target for s in samples]))
    return x, y


def predict(model, images, batch=64):
    import torch
    model.eval()
    outputs = []
    with torch.no_grad():
        for start in range(0, len(images), batch):
            outputs.append(model(torch.from_numpy(images[start:start + batch])).numpy())
    return np.concatenate(outputs)


def score(raw, samples):
    """Pose and well-centre errors on usable images, plus accept/reject rates against the labels."""
    details = [decode(r) for r in raw]
    usable = [i for i, s in enumerate(samples) if s.target[3] > 0.5]
    pose_mm, yaw_deg, well_mm = [], [], []
    for i in usable:
        s, d = samples[i], details[i]
        dx, dy, yaw = s.scene.dx, s.scene.dy, s.scene.yaw
        pose_mm.append(1000 * np.hypot(d.offset_x_m - dx, d.offset_y_m - dy))
        yaw_deg.append(np.degrees(abs(d.yaw_rad - yaw)))
        error = np.linalg.norm(wells_at(d.offset_x_m, d.offset_y_m, d.yaw_rad)
                               - wells_at(dx, dy, yaw), axis=1)
        well_mm.append(1000 * error)
    well_mm = np.concatenate(well_mm)
    accepted = np.array([d.trusted(DEFAULT_MIN_CONFIDENCE) for d in details])
    labels = np.array([s.target[3] > 0.5 for s in samples])
    return {
        'images': len(samples),
        'usable_images': int(labels.sum()),
        'pose_error_mm_mean': float(np.mean(pose_mm)),
        'pose_error_mm_p95': float(np.percentile(pose_mm, 95)),
        'yaw_error_deg_mean': float(np.mean(yaw_deg)),
        'well_error_mm_mean': float(well_mm.mean()),
        'well_error_mm_p95': float(np.percentile(well_mm, 95)),
        'well_error_mm_max': float(well_mm.max()),
        'min_confidence': DEFAULT_MIN_CONFIDENCE,
        'accepted_usable_fraction': float(accepted[labels].mean()),
        'false_accept_fraction': float(accepted[~labels].mean()) if (~labels).any() else 0.0,
    }


def train(output, epochs=20, samples=1500, seed=0, held_out=300, verbose=True, world=None):
    import torch
    from gantry_vision.model import PlateNet
    torch.manual_seed(seed)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    camera = load_camera(world)
    model = PlateNet()
    optimiser = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimiser, max_lr=2e-3, total_steps=epochs * ((samples + 31) // 32))
    rng_seed = seed + 1
    history = []
    for epoch in range(epochs):
        # Fresh scenes every epoch: the detector never sees the same frame twice.
        batch_samples = make_set(camera, samples, seed=rng_seed + epoch)
        model.train()
        losses = []
        for start in range(0, samples, 32):
            x, y = _train_batch(batch_samples[start:start + 32])
            out = model(x)
            present = y[:, 4] > 0.5
            pose_loss = torch.nn.functional.smooth_l1_loss(out[present, :3], y[present, :3]) if present.any() \
                else out.sum() * 0
            presence_loss = torch.nn.functional.binary_cross_entropy_with_logits(out[:, 3], y[:, 3])
            loss = pose_loss + presence_loss
            optimiser.zero_grad()
            loss.backward()
            optimiser.step()
            scheduler.step()
            losses.append(float(loss.detach()))
        history.append(float(np.mean(losses)))
        if verbose:
            print(f'epoch {epoch + 1}/{epochs} loss {history[-1]:.4f}', flush=True)
    held = make_set(camera, held_out, seed=HELD_OUT_SEED, spread=HELD_OUT_SPREAD)
    metrics = score(predict(model, _images(held)), held)
    metrics['train_loss_history'] = [round(v, 4) for v in history]
    metrics['held_out_spread'] = HELD_OUT_SPREAD
    model_path = output / 'well_detector.onnx'
    export(model, model_path)
    metrics['onnx_matches_torch_max_abs_diff'] = onnx_parity(model, model_path, held[:8])
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n')
    return metrics


def export(model, path):
    import torch
    model.eval()
    dummy = torch.zeros(1, 3, 240, 320)
    torch.onnx.export(model, dummy, str(path), input_names=['image'], output_names=['pose'],
                      opset_version=17, dynamo=False)


def onnx_parity(model, path, samples):
    from gantry_vision.inference import PlateDetector
    session = PlateDetector(path)
    worst = 0.0
    torch_out = predict(model, _images(samples))
    for sample, expected in zip(samples, torch_out):
        got = session.session.run(None, {session.input_name: preprocess(sample.image)})[0][0]
        worst = max(worst, float(np.max(np.abs(got - expected))))
    return worst


def main():
    parser = argparse.ArgumentParser(description='Train and export the well-plate detector')
    parser.add_argument('--output', default='artifacts/vision')
    parser.add_argument('--epochs', type=int, default=20)
    parser.add_argument('--samples', type=int, default=1500)
    parser.add_argument('--world', default=None, help='lab_vision.sdf; defaults to this repository copy')
    args = parser.parse_args()
    metrics = train(args.output, epochs=args.epochs, samples=args.samples, world=args.world)
    print(json.dumps({k: v for k, v in metrics.items() if k != 'train_loss_history'}, indent=2))


if __name__ == '__main__':
    main()
