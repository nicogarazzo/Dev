"""Cancion de prueba para la UI: 1 minuto con las cuatro secciones que el cerebro distingue.

calm (voz sola) -> build (hats y snare entran) -> drop (todo + sub) -> break (sin bombo) -> drop
"""
from __future__ import annotations

import numpy as np

from avi.audio.synth import drum_loop

SECTIONS = (
    # nombre, segundos, argumentos de drum_loop
    ("calm", 12.0, dict(kick_gain=0.0, bass_hz=None, hats=False, snares=False, voice_hz=330.0)),
    ("build", 12.0, dict(kick_gain=0.45, bass_hz=110.0, hats=True, snares=True, voice_hz=440.0)),
    ("drop", 16.0, dict(kick_gain=1.0, bass_hz=55.0, hats=True, snares=True, sub_hz=41.0, voice_hz=660.0)),
    ("break", 8.0, dict(kick_gain=0.0, bass_hz=82.0, hats=True, snares=False, voice_hz=495.0)),
    ("drop", 12.0, dict(kick_gain=1.0, bass_hz=55.0, hats=True, snares=True, sub_hz=41.0, voice_hz=660.0)),
)


def demo_song(bpm: float = 126.0, sr: int = 48000) -> tuple[np.ndarray, list[dict]]:
    """Devuelve (audio mono float32, [{name, start, end}]). Cada seccion dura un numero entero de compases."""
    bar = 4 * 60.0 / bpm
    parts, marks, t = [], [], 0.0
    for name, seconds, kw in SECTIONS:
        seconds = round(seconds / bar) * bar
        part = drum_loop(seconds, bpm, sr, **kw)
        # Cada parte viene normalizada a 0.9: el calm y el break suenan mas suaves a proposito.
        gain = {"calm": 0.55, "build": 0.8, "break": 0.65}.get(name, 1.0)
        parts.append(part * gain)
        marks.append({"name": name, "start": round(t, 3), "end": round(t + seconds, 3)})
        t += seconds
    audio = np.concatenate(parts).astype(np.float32)
    # Fundido corto entre partes para que no hagan click.
    fade = int(0.01 * sr)
    for m in marks[1:]:
        i = int(m["start"] * sr)
        if fade < i < len(audio) - fade:
            audio[i - fade:i] *= np.linspace(1.0, 0.0, fade)
            audio[i:i + fade] *= np.linspace(0.0, 1.0, fade)
    return audio, marks


def resample(audio: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Remuestreo por FFT (suficiente para escuchar la demo en el navegador)."""
    if sr_in == sr_out:
        return audio
    n_out = int(round(len(audio) * sr_out / sr_in))
    spec = np.fft.rfft(audio)
    keep = n_out // 2 + 1
    spec = spec[:keep] if len(spec) >= keep else np.pad(spec, (0, keep - len(spec)))
    out = np.fft.irfft(spec, n_out) * (n_out / len(audio))
    return out.astype(np.float32)
