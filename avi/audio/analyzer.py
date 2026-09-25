"""Analyzer: bloques de audio -> AnalysisFrame (instrumentos, golpes, BPM, compas).

Es la entrada del cerebro (F2). Funciona igual en vivo (bloques de sounddevice) y
offline (`avi analyze cancion.wav`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from .spectrogram import Spectrogram, to_mono
from .tempo import TempoTracker
from .trackers import TrackerBank, TrackerState, configs_from_yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "config" / "bands.yaml"


@dataclass
class AnalysisFrame:
    t: float
    instruments: dict[str, TrackerState]
    onset_strength: float
    bpm: float
    beat: int
    bar: int
    on_beat: bool
    phrase_pos: float
    loudness: float

    def as_dict(self) -> dict:
        return {
            "t": round(self.t, 4),
            "bpm": round(self.bpm, 2),
            "beat": self.beat,
            "bar": self.bar,
            "on_beat": self.on_beat,
            "phrase_pos": round(self.phrase_pos, 4),
            "loudness": round(self.loudness, 4),
            "onset_strength": round(self.onset_strength, 5),
            "instruments": {k: v.as_dict() for k, v in self.instruments.items()},
        }


def load_config(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Analyzer:
    def __init__(self, config: dict | None = None, sample_rate: int | None = None):
        cfg = config or load_config()
        self.sample_rate = int(sample_rate or cfg.get("sample_rate", 48000))
        fft_size = int(cfg.get("fft_size", 2048))
        hop = int(cfg.get("hop_size", cfg.get("block_size", 512)))
        self.spectrogram = Spectrogram(self.sample_rate, fft_size, hop)
        tracker_cfgs, adapt = configs_from_yaml(cfg)
        self.bank = TrackerBank(tracker_cfgs, self.spectrogram.freqs, self.spectrogram.frame_rate, adapt)
        self.tempo = TempoTracker(self.spectrogram.frame_rate)
        self._frames = 0
        self._loud_ref = 1e-6
        self._loud_decay = np.exp(-1.0 / (self.spectrogram.frame_rate * 6.0))
        self.last: AnalysisFrame | None = None

    @property
    def frame_rate(self) -> float:
        return self.spectrogram.frame_rate

    def process(self, samples: np.ndarray) -> list[AnalysisFrame]:
        """Agrega un bloque de audio y devuelve un AnalysisFrame por espectro completo."""
        out = []
        for power in self.spectrogram.push(to_mono(samples)):
            out.append(self._process_spectrum(power))
        return out

    def _process_spectrum(self, power: np.ndarray) -> AnalysisFrame:
        self._frames += 1
        states = self.bank.process(power)
        # Fuerza de golpe global: suma de los flujos de los rastreadores transitorios.
        onset_strength = 0.0
        for tracker in self.bank.trackers:
            if tracker.cfg.is_transient:
                onset_strength += tracker.state.raw * (1.0 if tracker.state.onset else 0.0)
                onset_strength += tracker.state.raw * 0.1
        self.tempo.push(onset_strength)
        loud_raw = float(np.sqrt(power.sum()))
        self._loud_ref = max(loud_raw, self._loud_ref * self._loud_decay, 1e-6)
        loudness = min(1.0, loud_raw / self._loud_ref)
        frame = AnalysisFrame(
            t=self.spectrogram.time_of_frame(self._frames),
            instruments=states,
            onset_strength=onset_strength,
            bpm=self.tempo.bpm,
            beat=self.tempo.beat,
            bar=self.tempo.bar,
            on_beat=self.tempo.on_beat,
            phrase_pos=self.tempo.phrase_pos(),
            loudness=loudness,
        )
        self.last = frame
        return frame


def analyze_signal(samples: np.ndarray, sample_rate: int, config: dict | None = None, block_size: int = 512) -> list[AnalysisFrame]:
    """Analiza una senal completa en bloques, como si llegara en vivo."""
    cfg = dict(config or load_config())
    cfg["sample_rate"] = sample_rate
    analyzer = Analyzer(cfg, sample_rate)
    frames: list[AnalysisFrame] = []
    mono = to_mono(samples)
    for start in range(0, len(mono), block_size):
        frames.extend(analyzer.process(mono[start:start + block_size]))
    return frames


def summarize(frames: list[AnalysisFrame]) -> dict:
    """Resumen para humanos: BPM final, golpes por instrumento y rango final de cada rastreador."""
    if not frames:
        return {}
    names = list(frames[-1].instruments.keys())
    onsets = {n: sum(1 for f in frames if f.instruments[n].onset) for n in names}
    levels = {n: round(float(np.mean([f.instruments[n].level for f in frames])), 3) for n in names}
    hz = {n: frames[-1].instruments[n].as_dict()["hz"] for n in names}
    return {
        "seconds": round(frames[-1].t, 2),
        "frames": len(frames),
        "bpm": round(frames[-1].bpm, 1),
        "onsets": onsets,
        "mean_level": levels,
        "final_hz": hz,
    }
