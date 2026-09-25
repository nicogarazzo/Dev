"""BPM, fase del beat y compas a partir de la envolvente de golpes."""
from __future__ import annotations

import numpy as np


class TempoTracker:
    """Estima el BPM por autocorrelacion de la envolvente de golpes (ultimos `window_s`),
    con peine de multiplos y un prior log-normal alrededor de `prior_bpm` para evitar
    errores de octava. La fase se sigue con un PLL suave: `is_beat` marca el frame en
    que cae cada beat y `beat` cuenta 1..4 dentro del compas.
    """

    def __init__(self, frame_rate: float, bpm_range=(70.0, 180.0), prior_bpm: float = 120.0,
                 window_s: float = 8.0, update_s: float = 0.5, min_history_s: float = 4.0,
                 lead_frames: float = 0.0):
        self.fr = frame_rate
        # Los golpes se detectan ~media ventana FFT tarde; el beat predicho se adelanta
        # eso para caer cuando realmente suena el golpe.
        self.lead = lead_frames
        self.bpm_grid = np.arange(bpm_range[0], bpm_range[1] + 1e-9, 0.25)
        self.prior = np.exp(-0.5 * (np.log2(self.bpm_grid / prior_bpm) / 1.0) ** 2)
        self.n = int(round(window_s * frame_rate))
        self.update_every = max(1, int(round(update_s * frame_rate)))
        self.min_hist = int(round(min_history_s * frame_rate))
        self.env = np.zeros(self.n)
        self.low = np.zeros(self.n)  # energia grave por frame, para ubicar el downbeat
        self.count = 0

        self.bpm: float | None = None
        self._candidate: float | None = None
        self.next_beat: float | None = None  # en frames absolutos
        self.beat_count = -1
        self.downbeat_offset = 0
        self._pos_energy = np.zeros(4)
        self._beat_low = 0.0

    @property
    def period(self) -> float | None:
        return 60.0 * self.fr / self.bpm if self.bpm else None

    def push(self, onset_strength: float, low_energy: float = 0.0) -> bool:
        """Agrega un frame. Devuelve True si en este frame cae un beat."""
        self.env[:-1] = self.env[1:]
        self.env[-1] = onset_strength
        self.low[:-1] = self.low[1:]
        self.low[-1] = low_energy
        self.count += 1
        self._beat_low = max(self._beat_low, low_energy)
        if self.count >= self.min_hist and self.count % self.update_every == 0:
            self._estimate()
        return self._advance()

    # ------------------------------------------------------------------ estimate
    def _estimate(self) -> None:
        e = self.env[-min(self.count, self.n):]
        e = e - e.mean()
        if not np.any(e):
            return
        spec = np.fft.rfft(e, 2 * len(e))
        ac = np.fft.irfft(spec * np.conj(spec))[: len(e)]
        if ac[0] <= 0:
            return
        ac = ac / ac[0]
        lags = 60.0 * self.fr / self.bpm_grid
        score = np.zeros_like(lags)
        for m, w in ((1, 1.0), (2, 0.5), (3, 0.33), (4, 0.25)):
            L = lags * m
            ok = L < len(ac) - 1
            score[ok] += w * np.interp(L[ok], np.arange(len(ac)), ac)
        score *= self.prior
        new = float(self.bpm_grid[np.argmax(score)])
        if score.max() <= 0:
            return
        if self.bpm is None:
            self.bpm = new
        elif abs(new - self.bpm) / self.bpm < 0.04:
            self.bpm = 0.7 * self.bpm + 0.3 * new
            self._candidate = None
        elif self._candidate is not None and abs(new - self._candidate) / self._candidate < 0.04:
            self.bpm, self._candidate = new, None  # cambio sostenido 2 veces: se acepta
        else:
            self._candidate = new
        self._correct_phase()

    def _correct_phase(self) -> None:
        P = self.period
        hist = min(self.count, self.n, int(4 * P) + 1)
        e = self.env[-hist:]
        idx = np.arange(hist)
        phases = np.arange(0, P, 0.5)
        # fase = cuantos frames atras cayo el ultimo beat
        score = [np.interp(hist - 1 - (ph + np.arange(0, hist - ph, P)), idx, e).sum() for ph in phases]
        last_beat = self.count - 1 - phases[int(np.argmax(score))]
        predicted = last_beat + P
        while predicted <= self.count - 1:
            predicted += P
        if self.next_beat is None:
            self.next_beat = predicted
            return
        err = (predicted - self.next_beat + P / 2) % P - P / 2
        self.next_beat += 0.3 * err

    # ------------------------------------------------------------------ advance
    def _advance(self) -> bool:
        if self.next_beat is None or self.count - 1 < self.next_beat - 0.5 - self.lead:
            return False
        self.next_beat += self.period
        self.beat_count += 1
        # energia grave del beat anterior, por posicion en el compas
        pos = (self.beat_count - 1) % 4
        self._pos_energy[pos] = 0.9 * self._pos_energy[pos] + 0.1 * self._beat_low
        self._beat_low = 0.0
        if self.beat_count % 16 == 0 and self.beat_count:
            best = int(np.argmax(self._pos_energy))
            if self._pos_energy[best] > 1.2 * self._pos_energy[self.downbeat_offset]:
                self.downbeat_offset = best
        return True

    @property
    def beat(self) -> int:
        """1..4 dentro del compas (0 si aun no hay tempo)."""
        if self.beat_count < 0:
            return 0
        return (self.beat_count - self.downbeat_offset) % 4 + 1

    @property
    def bar(self) -> int:
        if self.beat_count < 0:
            return 0
        return (self.beat_count - self.downbeat_offset) // 4 + 1

    @property
    def phase(self) -> float:
        """0..1 dentro del beat actual."""
        if self.next_beat is None:
            return 0.0
        return float(np.clip(1.0 - (self.next_beat - self.lead - (self.count - 1)) / self.period, 0.0, 1.0))

    def phrase_pos(self, beats_per_phrase: int = 16) -> float:
        """0..1 dentro de la frase (16 beats por defecto); el cerebro cuantiza ahi los cambios."""
        if self.beat_count < 0:
            return 0.0
        pos = (self.beat_count - self.downbeat_offset) % beats_per_phrase
        return (pos + self.phase) / beats_per_phrase
