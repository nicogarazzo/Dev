"""Pistas sinteticas con verdad conocida, para tests y `avi demo`."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def kick(sr: float, dur: float = 0.3) -> np.ndarray:
    t = np.arange(int(dur * sr)) / sr
    f = 45 + 75 * np.exp(-t / 0.04)  # barrido 120 -> 45 Hz
    phase = 2 * np.pi * np.cumsum(f) / sr
    return np.sin(phase) * np.exp(-t / 0.12)


def _band_noise(sr: float, dur: float, lo: float, hi: float, decay: float, rng) -> np.ndarray:
    n = int(dur * sr)
    spec = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / sr)
    spec[(f < lo) | (f > hi)] = 0
    x = np.fft.irfft(spec, n)
    x /= np.abs(x).max() + 1e-12
    return x * np.exp(-np.arange(n) / sr / decay)


def snare(sr: float, rng) -> np.ndarray:
    body = _band_noise(sr, 0.2, 1500, 7000, 0.06, rng)
    t = np.arange(len(body)) / sr
    return 0.7 * body + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)


def hat(sr: float, rng) -> np.ndarray:
    return _band_noise(sr, 0.08, 7000, 16000, 0.015, rng)


def saw(f0: float, t: np.ndarray, harmonics: int = 6) -> np.ndarray:
    return sum(np.sin(2 * np.pi * f0 * h * t) / h for h in range(1, harmonics + 1))


@dataclass
class SynthTrack:
    audio: np.ndarray
    sample_rate: int
    bpm: float
    onsets: dict[str, list[float]] = field(default_factory=dict)
    stems: dict[str, np.ndarray] = field(default_factory=dict)


def make_track(bpm: float = 128.0, seconds: float = 16.0, sr: int = 48000,
               parts=("kick", "bass", "snare", "hats"), bass_hz=(110.0, 98.0, 123.5, 82.4),
               seed: int = 0) -> SynthTrack:
    """Four-on-the-floor: bombo en cada beat, snare en 2 y 4, hats a contratiempo,
    bajo sostenido (cambia de nota cada compas) que comparte graves con el bombo,
    y un pad en la zona de voz."""
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    beat = 60.0 / bpm
    stems: dict[str, np.ndarray] = {}
    onsets: dict[str, list[float]] = {}

    def place(name: str, sample: np.ndarray, times, gain: float):
        y = np.zeros(n)
        for tt in times:
            i = int(round(tt * sr))
            m = min(len(sample), n - i)
            if m > 0:
                y[i:i + m] += gain * sample[:m]
        stems[name] = y
        onsets[name] = [float(tt) for tt in times]

    beats = np.arange(0, seconds - 0.05, beat)
    if "kick" in parts:
        place("kick", kick(sr), beats, 0.8)
    if "snare" in parts:
        place("snare", snare(sr, rng), beats[1::2], 0.35)
    if "hats" in parts:
        place("hats", hat(sr, rng), beats + beat / 2, 0.2)
    t = np.arange(n) / sr
    if "bass" in parts:
        bar = (t // (4 * beat)).astype(int) % len(bass_hz)
        f0 = np.asarray(bass_hz)[bar]
        phase = 2 * np.pi * np.cumsum(f0) / sr
        stems["bass"] = 0.25 * sum(np.sin(h * phase) / h for h in range(1, 7))
    if "pad" in parts:
        stems["pad"] = 0.08 * (saw(440.0, t, 4) + saw(660.0, t, 3))
    audio = sum(stems.values()) if stems else np.zeros(n)
    return SynthTrack(audio=np.asarray(audio), sample_rate=sr, bpm=bpm, onsets=onsets, stems=stems)
