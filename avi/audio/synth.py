"""Audio sintetico para tests y demos: bombo, bajo, snare, hats, sub y voz.

Sin hardware ni canciones con derechos: con esto se prueba que los rastreadores
separan instrumentos superpuestos y que el BPM se detecta.

- `drum_loop` / `song`: loop 4/4 y cancion de juguete calm -> build -> drop (`avi synth`).
- `make_track`: pista con la verdad conocida (golpes por instrumento y stems), para medir
  recall/precision de golpes y separacion (`avi demo`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def _t(seconds: float, sr: int) -> np.ndarray:
    return np.arange(int(seconds * sr)) / sr


def kick(sr: int, length_s: float = 0.25, f_start: float = 150.0, f_end: float = 50.0) -> np.ndarray:
    t = _t(length_s, sr)
    freq = f_end + (f_start - f_end) * np.exp(-t * 30.0)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    env = np.exp(-t * 12.0)
    return (np.sin(phase) * env).astype(np.float32)


def snare(sr: int, length_s: float = 0.18) -> np.ndarray:
    t = _t(length_s, sr)
    rng = np.random.default_rng(1)
    noise = rng.standard_normal(len(t))
    # Pasa banda tosco 2-6 kHz: diferencia de medias moviles.
    noise = bandpass_noise(noise, sr, 2000.0, 6000.0)
    body = np.sin(2 * np.pi * 190.0 * t) * np.exp(-t * 25.0) * 0.4
    return ((noise * np.exp(-t * 18.0) * 0.6) + body).astype(np.float32)


def hat(sr: int, length_s: float = 0.06) -> np.ndarray:
    t = _t(length_s, sr)
    rng = np.random.default_rng(2)
    noise = bandpass_noise(rng.standard_normal(len(t)), sr, 6000.0, 16000.0)
    return (noise * np.exp(-t * 60.0) * 0.5).astype(np.float32)


def bandpass_noise(noise: np.ndarray, sr: int, low: float, high: float) -> np.ndarray:
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(len(noise), 1.0 / sr)
    spec[(freqs < low) | (freqs > high)] = 0
    out = np.fft.irfft(spec, len(noise))
    peak = np.abs(out).max()
    return out / peak if peak > 0 else out


def bass_note(sr: int, freq: float, length_s: float, harmonics: int = 4) -> np.ndarray:
    t = _t(length_s, sr)
    out = np.zeros_like(t)
    for h in range(1, harmonics + 1):
        out += np.sin(2 * np.pi * freq * h * t) / (h ** 1.5)
    env = np.minimum(1.0, t * 200.0) * np.exp(-t * 2.0)
    return (out * env * 0.5).astype(np.float32)


def sub_tone(sr: int, freq: float, length_s: float) -> np.ndarray:
    t = _t(length_s, sr)
    return (np.sin(2 * np.pi * freq * t) * 0.6).astype(np.float32)


def voice_tone(sr: int, freq: float, length_s: float) -> np.ndarray:
    """Tono armonico con vibrato, parecido a una voz o synth sostenido."""
    t = _t(length_s, sr)
    # Vibrato como modulacion de fase: +-0.5 % de la frecuencia a 5.5 Hz.
    vib = (0.005 * freq / 5.5) * np.sin(2 * np.pi * 5.5 * t)
    out = np.zeros_like(t)
    for h in range(1, 7):
        out += np.sin(2 * np.pi * h * (freq * t + vib)) / h
    return (out * 0.25).astype(np.float32)


def place(canvas: np.ndarray, clip: np.ndarray, at_s: float, sr: int, gain: float = 1.0) -> None:
    start = int(at_s * sr)
    end = min(len(canvas), start + len(clip))
    if start < len(canvas):
        canvas[start:end] += clip[: end - start] * gain


def drum_loop(seconds: float = 12.0, bpm: float = 126.0, sr: int = 48000, kick_gain: float = 1.0,
              bass_hz: float | None = 110.0, hats: bool = True, snares: bool = True,
              sub_hz: float | None = None, voice_hz: float | None = None, seed: int = 0) -> np.ndarray:
    """Loop 4/4: bombo en cada beat, snare en 2 y 4, hats en corcheas, bajo en negras."""
    canvas = np.zeros(int(seconds * sr), dtype=np.float32)
    beat = 60.0 / bpm
    n_beats = int(seconds / beat) + 1
    k = kick(sr)
    s = snare(sr)
    h = hat(sr)
    for i in range(n_beats):
        t0 = i * beat
        place(canvas, k, t0, sr, kick_gain)
        if snares and i % 2 == 1:
            place(canvas, s, t0, sr, 0.7)
        if hats:
            place(canvas, h, t0 + beat / 2, sr, 0.5)
            place(canvas, h, t0, sr, 0.3)
        if bass_hz:
            place(canvas, bass_note(sr, bass_hz, beat * 0.9), t0 + beat * 0.02, sr, 0.8)
    if sub_hz:
        canvas += sub_tone(sr, sub_hz, seconds)[: len(canvas)]
    if voice_hz:
        canvas += voice_tone(sr, voice_hz, seconds)[: len(canvas)]
    peak = np.abs(canvas).max()
    return (canvas / peak * 0.9).astype(np.float32) if peak > 0 else canvas


def song(seconds: float = 30.0, bpm: float = 126.0, sr: int = 48000) -> np.ndarray:
    """Cancion de juguete: calm (sin bombo) -> build (hats y snare suben) -> drop (todo)."""
    canvas = np.zeros(int(seconds * sr), dtype=np.float32)
    third = seconds / 3
    calm = drum_loop(third, bpm, sr, kick_gain=0.0, bass_hz=None, hats=False, snares=False, voice_hz=330.0)
    build = drum_loop(third, bpm, sr, kick_gain=0.5, bass_hz=110.0, hats=True, snares=True, voice_hz=440.0)
    drop = drum_loop(third, bpm, sr, kick_gain=1.0, bass_hz=55.0, hats=True, snares=True, sub_hz=40.0, voice_hz=660.0)
    for i, part in enumerate((calm, build, drop)):
        start = int(i * third * sr)
        canvas[start:start + len(part)] += part[: len(canvas) - start]
    peak = np.abs(canvas).max()
    return canvas / peak * 0.9 if peak > 0 else canvas


# --- Pistas con verdad conocida -------------------------------------------------

def _kick_sweep(sr: float, dur: float = 0.3) -> np.ndarray:
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


def _snare_burst(sr: float, rng) -> np.ndarray:
    body = _band_noise(sr, 0.2, 1500, 7000, 0.06, rng)
    t = np.arange(len(body)) / sr
    return 0.7 * body + 0.3 * np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)


def _hat_burst(sr: float, rng) -> np.ndarray:
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

    def put(name: str, sample: np.ndarray, times, gain: float):
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
        put("kick", _kick_sweep(sr), beats, 0.8)
    if "snare" in parts:
        put("snare", _snare_burst(sr, rng), beats[1::2], 0.35)
    if "hats" in parts:
        put("hats", _hat_burst(sr, rng), beats + beat / 2, 0.2)
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
