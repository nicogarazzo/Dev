"""Lectura/escritura de audio sin dependencias extra (WAV PCM con `wave`).

Si `soundfile` esta instalado se usa primero, y entonces tambien sirven FLAC/OGG/WAV float.
Para MP3 u otros: conviertelo antes (`ffmpeg -i cancion.mp3 cancion.wav`).
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np


def read_audio(path: str | Path) -> tuple[np.ndarray, int]:
    """Devuelve (mono float64 en -1..1, sample_rate)."""
    path = Path(path)
    try:
        import soundfile as sf  # type: ignore

        data, sr = sf.read(str(path), dtype="float64", always_2d=True)
        return data.mean(axis=1), int(sr)
    except ImportError:
        pass
    with wave.open(str(path), "rb") as w:
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float64) - 128) / 128
    elif width == 2:
        x = np.frombuffer(raw, "<i2") / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif width == 4:
        x = np.frombuffer(raw, "<i4") / float(1 << 31)
    else:
        raise ValueError(f"WAV de {8 * width} bits no soportado")
    return x.reshape(-1, ch).mean(axis=1), sr


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int) -> Path:
    """Escribe mono 16 bits, normalizando si pasa de 1.0."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(audio, dtype=np.float64)
    peak = np.abs(x).max() if len(x) else 0
    if peak > 1:
        x = x / peak
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return path
