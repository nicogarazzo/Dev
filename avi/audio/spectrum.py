"""Espectrograma en streaming y separacion percusivo / armonico causal."""
from __future__ import annotations

from collections import deque
from collections.abc import Iterator

import numpy as np


class StreamingSTFT:
    """Recibe bloques de cualquier tamano y entrega un espectro de magnitud por hop.

    La magnitud esta normalizada para que un seno de amplitud 1 de ~1.0 en su bin.
    El frame i representa la ventana que termina en la muestra (i + 1) * hop.
    """

    def __init__(self, fft_size: int = 2048, hop_size: int = 512):
        if fft_size % hop_size:
            raise ValueError("fft_size debe ser multiplo de hop_size")
        self.fft_size = fft_size
        self.hop_size = hop_size
        self.window = np.hanning(fft_size)
        self.norm = 2.0 / self.window.sum()
        self._frame = np.zeros(fft_size)
        self._pending = np.zeros(0)

    def push(self, samples: np.ndarray) -> Iterator[np.ndarray]:
        x = np.asarray(samples, dtype=np.float64)
        if x.ndim > 1:
            x = x.mean(axis=1)
        x = np.concatenate([self._pending, x])
        hop = self.hop_size
        n = len(x) // hop
        for i in range(n):
            self._frame[:-hop] = self._frame[hop:]
            self._frame[-hop:] = x[i * hop:(i + 1) * hop]
            yield np.abs(np.fft.rfft(self._frame * self.window)) * self.norm
        self._pending = x[n * hop:]

    def freqs(self, sample_rate: float) -> np.ndarray:
        return np.fft.rfftfreq(self.fft_size, 1.0 / sample_rate)


class CausalHPSS:
    """Separa cada frame en parte armonica (lo que se sostiene) y percusiva (lo nuevo).

    Armonico = mediana de los ultimos `frames` espectros (incluido el actual), recortada
    al frame actual. Percusivo = el resto. La suma de ambas partes es el frame original,
    asi que la energia se reparte, nunca se duplica.
    """

    def __init__(self, frames: int = 9):
        self.frames = max(1, int(frames))
        self._hist: deque[np.ndarray] = deque(maxlen=self.frames)

    def push(self, mag: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not self._hist:
            # Antes del primer frame hubo silencio: lo que suena al arrancar es un golpe.
            self._hist.extend(np.zeros_like(mag) for _ in range(self.frames - 1))
        self._hist.append(mag)
        harm = np.minimum(np.median(np.stack(self._hist), axis=0), mag)
        return mag - harm, harm
