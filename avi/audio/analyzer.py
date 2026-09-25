"""Analizador en streaming: audio -> un AudioFrame por hop (~10.7 ms a 48 kHz).

    an = Analyzer()                 # config/bands.yaml
    for frame in an.process(block): # bloques de cualquier tamano
        frame.instruments["kick"].level

Mismo codigo para archivo (avi analyze) y entrada en vivo (avi listen).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .config import AnalyzerConfig
from .onsets import OnsetDetector
from .spectrum import CausalHPSS, StreamingSTFT
from .tempo import TempoTracker
from .trackers import EPS, TrackerBank


@dataclass
class InstrumentState:
    level: float
    onset: bool
    hz: tuple[float, float]
    confidence: float

    def to_dict(self) -> dict:
        return {
            "level": round(self.level, 4),
            "onset": self.onset,
            "hz": [int(round(self.hz[0])), int(round(self.hz[1]))],
            "confidence": round(self.confidence, 3),
        }


@dataclass
class AudioFrame:
    t: float
    instruments: dict[str, InstrumentState]
    bpm: float | None
    beat: int              # 1..4 (0 = sin tempo aun)
    bar: int
    is_beat: bool          # True en el frame donde cae el beat
    beat_phase: float      # 0..1 dentro del beat
    energy: float          # 0..1, energia corta (~0.3 s) relativa al pico reciente
    energy_long: float     # 0..1, energia larga (~8 s); el cerebro compara ambas
    loudness_db: float     # dBFS del frame
    centroid_hz: float
    brightness: float      # 0..1, centroide en escala log de 200 Hz a 8 kHz
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "t": round(self.t, 4),
            "bpm": None if self.bpm is None else round(self.bpm, 2),
            "beat": self.beat,
            "bar": self.bar,
            "is_beat": self.is_beat,
            "beat_phase": round(self.beat_phase, 3),
            "energy": round(self.energy, 4),
            "energy_long": round(self.energy_long, 4),
            "loudness_db": round(self.loudness_db, 1),
            "centroid_hz": int(round(self.centroid_hz)),
            "brightness": round(self.brightness, 3),
            "instruments": {k: v.to_dict() for k, v in self.instruments.items()},
        }


def _ema_coef(tau_s: float, frame_rate: float) -> float:
    return 1.0 - np.exp(-1.0 / (tau_s * frame_rate))


class Analyzer:
    def __init__(self, cfg: AnalyzerConfig | None = None, sample_rate: float | None = None):
        self.cfg = cfg or AnalyzerConfig.load()
        self.sample_rate = float(sample_rate or self.cfg.sample_rate)
        self.stft = StreamingSTFT(self.cfg.fft_size, self.cfg.hop_size)
        self.hpss = CausalHPSS(self.cfg.hpss_frames)
        self.freqs = self.stft.freqs(self.sample_rate)
        self.frame_rate = self.sample_rate / self.cfg.hop_size
        self.bank = TrackerBank(self.cfg, self.freqs, self.frame_rate)
        K = len(self.cfg.trackers)
        self.onsets = OnsetDetector(
            K, self.frame_rate, k=self.cfg.onset_threshold_k,
            relative_min=self.cfg.onset_relative_min, min_interval_s=self.cfg.onset_min_interval_s,
        )
        self.tempo = TempoTracker(
            self.frame_rate, self.cfg.bpm_range, self.cfg.prior_bpm,
            self.cfg.tempo_window_s, self.cfg.tempo_update_s,
            lead_frames=self.cfg.fft_size / 2 / self.cfg.hop_size,
        )
        self.names = self.cfg.names
        self.report_onset = np.array([t.onset for t in self.cfg.trackers])
        self.low_idx = [i for i, n in enumerate(self.names) if n in ("sub", "kick", "bass")]

        # Peso de cada transitorio en la envolvente de tempo: 1 en graves, menos en agudos.
        centers = np.array([np.sqrt(t.nominal_hz[0] * t.nominal_hz[1]) for t in self.cfg.trackers])
        self.tempo_w = np.where(self.bank.transient, 1.0 / (1.0 + np.log2(np.maximum(centers, 100) / 100) / 2), 0.0)

        self.silence_amp = 10 ** (self.cfg.silence_db / 20)
        self.peak_decay = np.exp(-1.0 / (10.0 * self.frame_rate))
        self.peak = np.full(K, self.silence_amp * 10)
        self.level = np.zeros(K)
        self.e_short = 0.0
        self.e_long = 0.0
        self.e_peak = self.silence_amp * 10
        self.e_peak_decay = np.exp(-1.0 / (30.0 * self.frame_rate))
        self.a_short = _ema_coef(0.3, self.frame_rate)
        self.a_long = _ema_coef(8.0, self.frame_rate)
        self.band = (self.freqs >= 20) & (self.freqs <= 18000)
        self.n_frames = 0

    def process(self, samples: np.ndarray) -> list[AudioFrame]:
        return [self._frame(mag) for mag in self.stft.push(samples)]

    def _frame(self, mag: np.ndarray) -> AudioFrame:
        self.n_frames += 1
        t = self.n_frames * self.cfg.hop_size / self.sample_rate
        perc, harm = self.hpss.push(mag)

        amp = float(np.sqrt(np.sum(mag[self.band] ** 2)))
        silent = amp < self.silence_amp
        M = self.bank.separate(perc, harm)
        A = np.sqrt(np.sum(M**2, axis=1))

        # Golpes: la fuerza de un transitorio es su energia percusiva enmascarada.
        strength = np.where(self.bank.transient, A, 0.0)
        hits = self.onsets.push(strength, gate=not silent) & self.bank.transient
        self.bank.adapt(M, perc, harm, hits, silent)

        # Nivel 0..1 relativo al pico reciente de cada rastreador, con ataque/relajacion.
        self.peak = np.maximum(A, np.maximum(self.peak * self.peak_decay, self.silence_amp * 10))
        raw = np.zeros_like(A) if silent else np.clip(A / self.peak, 0.0, 1.0)
        coef = np.where(raw > self.level, self.cfg.attack, self.cfg.release)
        self.level = coef * self.level + (1 - coef) * raw

        # Tempo: envolvente = fuerza de golpe de cada transitorio relativa a su pico,
        # con mas peso en los graves (el bombo suele marcar el beat; los hats el contratiempo).
        env = float(self.tempo_w @ (strength / self.peak))
        low = float(A[self.low_idx].sum()) if self.low_idx else 0.0
        is_beat = self.tempo.push(0.0 if silent else env, low)

        # Energia global y color espectral.
        self.e_peak = max(amp, self.e_peak * self.e_peak_decay, self.silence_amp * 10)
        e = 0.0 if silent else amp / self.e_peak
        self.e_short += self.a_short * (e - self.e_short)
        self.e_long += self.a_long * (e - self.e_long)
        spec = mag[self.band]
        centroid = float((self.freqs[self.band] @ spec) / (spec.sum() + EPS)) if not silent else 0.0
        bright = float(np.clip(np.log2(max(centroid, 1.0) / 200.0) / np.log2(8000 / 200), 0.0, 1.0))

        instruments = {
            name: InstrumentState(
                level=float(self.level[k]),
                onset=bool(hits[k] and self.report_onset[k]),
                hz=self.bank.hz[k],
                confidence=float(self.bank.confidence[k]),
            )
            for k, name in enumerate(self.names)
        }
        return AudioFrame(
            t=t, instruments=instruments, bpm=self.tempo.bpm, beat=self.tempo.beat, bar=self.tempo.bar,
            is_beat=is_beat, beat_phase=self.tempo.phase, energy=self.e_short, energy_long=self.e_long,
            loudness_db=float(20 * np.log10(amp + EPS)), centroid_hz=centroid, brightness=bright,
        )


def analyze_array(samples: np.ndarray, sample_rate: float, cfg: AnalyzerConfig | None = None,
                  block_size: int = 4096) -> list[AudioFrame]:
    """Analiza un arreglo completo en bloques, igual que lo haria en vivo."""
    an = Analyzer(cfg, sample_rate)
    out: list[AudioFrame] = []
    for i in range(0, len(samples), block_size):
        out.extend(an.process(samples[i:i + block_size]))
    return out
