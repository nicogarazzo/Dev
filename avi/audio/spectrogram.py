"""Espectrograma en streaming: bloques de audio -> espectros de potencia.

Mantiene una ventana deslizante de `fft_size` muestras y produce un espectro por
cada `hop_size` muestras nuevas. Todo lo que arma numeros esta separado del I/O
para poder probarlo sin hardware.
"""
from __future__ import annotations

import numpy as np


class Spectrogram:
    def __init__(self, sample_rate: int = 48000, fft_size: int = 2048, hop_size: int = 512):
        self.sample_rate = sample_rate
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.window = np.hanning(fft_size).astype(np.float32)
        # Compensa la energia que quita la ventana para que el nivel no dependa de fft_size.
        self._norm = 1.0 / (self.window.sum() ** 2)
        self.freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
        self._buffer = np.zeros(fft_size, dtype=np.float32)
        self._pending = np.zeros(0, dtype=np.float32)
        self.frames_done = 0

    @property
    def frame_rate(self) -> float:
        """Espectros por segundo."""
        return self.sample_rate / self.hop_size

    def bin_range(self, low_hz: float, high_hz: float) -> np.ndarray:
        """Indices de bins cuya frecuencia central cae en [low_hz, high_hz]."""
        return np.where((self.freqs >= low_hz) & (self.freqs <= high_hz))[0]

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        """Agrega muestras (mono, float en -1..1) y devuelve los espectros completos."""
        samples = np.asarray(samples, dtype=np.float32).ravel()
        self._pending = np.concatenate([self._pending, samples])
        frames = []
        while len(self._pending) >= self.hop_size:
            chunk, self._pending = self._pending[: self.hop_size], self._pending[self.hop_size :]
            self._buffer = np.concatenate([self._buffer[self.hop_size :], chunk])
            frames.append(self._spectrum(self._buffer))
            self.frames_done += 1
        return frames

    def _spectrum(self, block: np.ndarray) -> np.ndarray:
        spec = np.fft.rfft(block * self.window)
        return (np.abs(spec) ** 2) * self._norm

    def time_of_frame(self, index: int) -> float:
        """Instante (s) del final de la ventana del espectro `index`."""
        return index * self.hop_size / self.sample_rate


def to_mono(samples: np.ndarray) -> np.ndarray:
    """Mezcla a mono un array (n,) o (n, canales)."""
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 2:
        return arr.mean(axis=1)
    return arr
