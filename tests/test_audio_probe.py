import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audio_probe import band_levels, load_bands  # noqa: E402


def test_band_levels_isolates_a_sine():
    bands = load_bands()
    sr, n = 48000, 4096
    t = np.arange(n) / sr
    block = 0.5 * np.sin(2 * np.pi * 100 * t)  # 100 Hz cae en "kick"
    lv = band_levels(block, sr, bands)
    assert lv["kick"] > 5 * max(v for k, v in lv.items() if k != "kick")
