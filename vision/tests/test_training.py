import json

import pytest

pytest.importorskip('torch')
pytest.importorskip('onnxruntime')

from gantry_vision.train import train  # noqa: E402


def test_tiny_training_run_exports_onnx_that_matches_torch(tmp_path):
    metrics = train(tmp_path, epochs=1, samples=64, held_out=16, verbose=False)
    assert (tmp_path / 'well_detector.onnx').stat().st_size > 1000
    assert metrics['onnx_matches_torch_max_abs_diff'] < 1e-3
    saved = json.loads((tmp_path / 'metrics.json').read_text())
    assert saved['images'] == 16 and 'well_error_mm_p95' in saved
