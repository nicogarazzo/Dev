"""Medidor de bandas en vivo (fase L1/L3) para comprobar que AVI escucha el loopback.

    python scripts/audio_probe.py --list
    python scripts/audio_probe.py --device "VB-Cable" --seconds 10

Imprime una barra por banda (config/bands.yaml) unas 10 veces por segundo.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_bands():
    cfg = yaml.safe_load((ROOT / "config" / "bands.yaml").read_text()) or {}
    bands = cfg.get("trackers") or cfg.get("bands") or {}
    out = []
    for name, rng in bands.items():
        lo, hi = (rng.get("nominal_hz") or rng["hz"]) if isinstance(rng, dict) else rng
        out.append((name, float(lo), float(hi)))
    return out


def band_levels(block: np.ndarray, sr: int, bands) -> dict:
    """Energía RMS por banda (0..1 aprox) de un bloque mono. Puro numpy, testeable."""
    if block.ndim > 1:
        block = block.mean(axis=1)
    n = len(block)
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft(block * win)) / (n / 2)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    levels = {}
    for name, lo, hi in bands:
        m = (freqs >= lo) & (freqs < hi)
        levels[name] = float(np.sqrt(np.mean(spec[m] ** 2))) if m.any() else 0.0
    return levels


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--device", default=None)
    p.add_argument("--seconds", type=float, default=10)
    p.add_argument("--block", type=int, default=2048)
    a = p.parse_args()

    import sounddevice as sd

    if a.list:
        print(sd.query_devices())
        return

    bands = load_bands()
    sr = 48000
    dev = a.device
    if dev is not None and not dev.isdigit():
        names = [d["name"] for d in sd.query_devices()]
        dev = next((i for i, n in enumerate(names) if dev.lower() in n.lower()), None)
        if dev is None:
            raise SystemExit(f"dispositivo no encontrado; usa --list")
    elif dev is not None:
        dev = int(dev)

    def cb(indata, frames, t, status):
        lv = band_levels(indata.copy(), sr, bands)
        line = "  ".join(f"{k}:{'#' * int(min(1, v * 8) * 20):<20}" for k, v in lv.items())
        sys.stdout.write("\r" + line[:200])
        sys.stdout.flush()

    with sd.InputStream(device=dev, channels=1, samplerate=sr, blocksize=a.block, callback=cb):
        sd.sleep(int(a.seconds * 1000))
    print()


if __name__ == "__main__":
    main()
