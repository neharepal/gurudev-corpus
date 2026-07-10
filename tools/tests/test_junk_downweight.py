# tools/tests/test_junk_downweight.py
import sys, os
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import retrieve

def test_quality_weight_downranks_junk():
    fused = np.array([0.030, 0.030, 0.030], dtype=np.float32)
    metas = [
        {"quality_score": 1.0},   # clean
        {"quality_score": 0.1},   # junk
        {},                        # missing -> treated as 1.0 (fail-open)
    ]
    out = retrieve.apply_quality_weights(fused, metas, enabled=True)
    assert out[1] < out[0]          # junk downweighted below clean
    assert out[2] == fused[2]        # missing score = no penalty

def test_disabled_is_identity():
    fused = np.array([0.03, 0.03], dtype=np.float32)
    metas = [{"quality_score": 0.1}, {"quality_score": 1.0}]
    out = retrieve.apply_quality_weights(fused, metas, enabled=False)
    assert np.allclose(out, fused)
