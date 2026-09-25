"""Espectro en bandas logaritmicas para dibujar en la UI (no se usa para decidir nada).

Corre su propia STFT liviana sobre el mismo audio que el analizador, para no tocar
avi/audio. Devuelve 0..1 por banda, relativo a un pico que baja despacio.
"""
from __future__ import annotations

import numpy as np


class SpectrumTap:
    def __init__(self, sample_rate: float, fft_size: int = 2048, hop_size: int = 512,
                 n_bands: int = 48, f_lo: float = 30.0, f_hi: float = 16000.0, range_db: float = 60.0):
        self.sample_rate = float(sample_rate)
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.window = np.hanning(fft_size)
        self.range_db = range_db
        freqs = np.fft.rfftfreq(fft_size, 1.0 / self.sample_rate)
        f_hi = min(f_hi, 0.5 * self.sample_rate * 0.98)
        edges = np.geomspace(f_lo, f_hi, n_bands + 1)
        self.centers = np.sqrt(edges[:-1] * edges[1:])
        # Cada banda toma al menos el bin mas cercano (las bandas graves son mas angostas que un bin).
        self._bins = []
        for lo, hi in zip(edges[:-1], edges[1:]):
            idx = np.where((freqs >= lo) & (freqs < hi))[0]
            if len(idx) == 0:
                idx = np.array([int(np.argmin(np.abs(freqs - np.sqrt(lo * hi))))])
            self._bins.append(idx)
        self._buf = np.zeros(fft_size)
        self._pending = np.zeros(0)
        self._peak_db = -30.0
        self._peak_decay_db = 6.0 * hop_size / self.sample_rate  # baja 6 dB por segundo

    def push(self, samples: np.ndarray) -> list[np.ndarray]:
        self._pending = np.concatenate([self._pending, np.asarray(samples, dtype=np.float64).ravel()])
        out = []
        while len(self._pending) >= self.hop_size:
            chunk, self._pending = self._pending[: self.hop_size], self._pending[self.hop_size:]
            self._buf = np.concatenate([self._buf[self.hop_size:], chunk])
            out.append(self._bands(np.abs(np.fft.rfft(self._buf * self.window))))
        return out

    def _bands(self, mag: np.ndarray) -> np.ndarray:
        power = np.array([float(np.mean(mag[idx] ** 2)) for idx in self._bins])
        db = 10.0 * np.log10(power + 1e-12)
        self._peak_db = max(float(db.max()), self._peak_db - self._peak_decay_db)
        return np.clip((db - (self._peak_db - self.range_db)) / self.range_db, 0.0, 1.0)
