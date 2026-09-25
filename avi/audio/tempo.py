"""BPM y posicion en el compas a partir de la fuerza de los golpes.

Autocorrelacion de la envolvente de onsets de los ultimos segundos, restringida a
60-180 BPM, y una fase de beat que se alinea con los golpes. Suficiente para
cuantizar cambios de escena; el BPM exacto de rekordbox llega despues del MVP.
"""
from __future__ import annotations

import numpy as np


class TempoTracker:
    def __init__(self, frame_rate: float, window_s: float = 6.0, min_bpm: float = 60.0, max_bpm: float = 180.0, beats_per_bar: int = 4):
        self.frame_rate = frame_rate
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm
        self.beats_per_bar = beats_per_bar
        self.window = int(window_s * frame_rate)
        self._env = np.zeros(self.window, dtype=np.float64)
        self._frame = 0
        self._update_every = max(1, int(0.5 * frame_rate))
        self.bpm = 0.0
        self._period = 0.0          # frames por beat
        self._phase = 0.0           # frame del ultimo beat estimado
        self.beat = 0               # beat dentro del compas (0..beats_per_bar-1)
        self.bar = 0
        self.beat_count = 0
        self._next_beat_frame = None
        self.on_beat = False

    def push(self, onset_strength: float) -> None:
        self._env = np.roll(self._env, -1)
        self._env[-1] = max(0.0, float(onset_strength))
        self._frame += 1
        self.on_beat = False
        if self._frame % self._update_every == 0 and self._frame >= self.window // 2:
            self._estimate()
        if self._period > 0:
            if self._next_beat_frame is None:
                self._next_beat_frame = self._frame + self._period
            if self._frame >= self._next_beat_frame:
                self.on_beat = True
                self.beat_count += 1
                self.beat = self.beat_count % self.beats_per_bar
                self.bar = self.beat_count // self.beats_per_bar
                self._next_beat_frame += self._period

    def _estimate(self) -> None:
        env = self._env - self._env.mean()
        if not np.any(env):
            return
        n = len(env)
        spec = np.fft.rfft(env, 2 * n)
        ac = np.fft.irfft(spec * np.conj(spec))[:n]
        if ac[0] <= 0:
            return
        ac = ac / ac[0]
        min_lag = int(self.frame_rate * 60.0 / self.max_bpm)
        max_lag = int(self.frame_rate * 60.0 / self.min_bpm)
        if max_lag <= min_lag + 2 or max_lag >= n:
            return
        lags = np.arange(min_lag, max_lag)
        scores = ac[min_lag:max_lag].copy()
        # Premia lags cuyo doble tambien resuena (evita elegir el medio tiempo).
        for i, lag in enumerate(lags):
            if 2 * lag < n:
                scores[i] += 0.5 * ac[2 * lag]
        # Preferencia suave por 90-160 BPM y por el lag mas corto entre los casi empatados
        # (evita caer al medio tiempo).
        bpms = 60.0 * self.frame_rate / lags
        scores = scores * np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.7) ** 2)
        top = scores.max()
        candidates = lags[scores >= 0.85 * top]
        best = int(candidates.min())
        if self.bpm > 0:
            # Si el candidato es la mitad o el doble del BPM actual, quedate en la octava actual.
            cand_bpm = 60.0 * self.frame_rate / best
            for factor in (0.5, 2.0):
                if abs(cand_bpm * factor - self.bpm) / self.bpm < 0.08:
                    best = int(round(best / factor))
                    break
        # Afina el lag con interpolacion parabolica.
        if 1 <= best < n - 1:
            y0, y1, y2 = ac[best - 1], ac[best], ac[best + 1]
            denom = (y0 - 2 * y1 + y2)
            offset = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
            best = best + float(np.clip(offset, -0.5, 0.5))
        new_bpm = 60.0 * self.frame_rate / best
        self.bpm = new_bpm if self.bpm == 0 else 0.7 * self.bpm + 0.3 * new_bpm
        self._period = 60.0 * self.frame_rate / self.bpm
        self._align_phase()

    def _align_phase(self) -> None:
        """Mueve el proximo beat al offset donde los golpes recientes caen mejor."""
        if self._period <= 0:
            return
        period = int(round(self._period))
        if period < 2:
            return
        tail = self._env[-4 * period :] if len(self._env) >= 4 * period else self._env
        best_off, best_score = 0, -1.0
        for off in range(period):
            score = tail[off::period].sum()
            if score > best_score:
                best_off, best_score = off, score
        # El ultimo golpe alineado ocurrio en (len(tail) - 1 - off) % period frames atras.
        since_last = (len(tail) - 1 - best_off) % period
        candidate = self._frame + (period - since_last)
        if self._next_beat_frame is None or abs(candidate - self._next_beat_frame) > 0.15 * period:
            self._next_beat_frame = candidate

    def phrase_pos(self, beats_per_phrase: int = 16) -> float:
        return (self.beat_count % beats_per_phrase) / beats_per_phrase
