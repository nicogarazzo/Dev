"""Deteccion de golpes por rastreador con umbral adaptativo."""
from __future__ import annotations

import numpy as np


class OnsetDetector:
    """Un golpe = la fuerza sube, supera media + k*desviacion reciente, supera una
    fraccion del pico reciente y ha pasado el periodo refractario.

    Trabaja sobre un vector (un valor por rastreador) para procesar todos a la vez.
    """

    def __init__(self, n: int, frame_rate: float, k: float = 1.5, relative_min: float = 0.2,
                 min_interval_s: float = 0.08, stats_s: float = 1.5, peak_s: float = 4.0):
        self.k = k
        self.relative_min = relative_min
        self.refractory = max(1, int(round(min_interval_s * frame_rate)))
        self.a = 1.0 / (stats_s * frame_rate)
        self.peak_decay = np.exp(-1.0 / (peak_s * frame_rate))
        self.mean = np.zeros(n)
        self.sq = np.zeros(n)
        self.peak = np.zeros(n)
        self.prev = np.zeros(n)
        self.since = np.full(n, 10**9)
        self.n = 0

    def push(self, strength: np.ndarray, gate: bool = True) -> np.ndarray:
        # Correccion de sesgo de la media movil: umbral util desde los primeros frames.
        corr = 1.0 - (1.0 - self.a) ** max(self.n, 1)
        mean, sq = self.mean / corr, self.sq / corr
        std = np.sqrt(np.maximum(sq - mean**2, 0.0))
        self.peak = np.maximum(strength, self.peak * self.peak_decay)
        hit = (
            gate
            & (strength > self.prev)
            & (strength > mean + self.k * std)
            & (self.n >= 2)
            & (strength > self.relative_min * self.peak)
            & (self.since >= self.refractory)
            & (strength > 0)
        )
        self.since = np.where(hit, 0, self.since + 1)
        self.mean += self.a * (strength - self.mean)
        self.sq += self.a * (strength**2 - self.sq)
        self.prev = strength
        self.n += 1
        return hit
