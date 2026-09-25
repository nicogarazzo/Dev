"""Configuracion del analisis (config/bands.yaml) como dataclasses."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "bands.yaml"

# Copia de config/bands.yaml por si el paquete se instala sin la carpeta config/.
_DEFAULT_TRACKERS = {
    "sub": {"nominal_hz": [20, 60], "search_hz": [20, 90], "character": "tonal", "onset": False},
    "kick": {"nominal_hz": [60, 150], "search_hz": [40, 200], "character": "transient", "onset": True},
    "bass": {"nominal_hz": [150, 400], "search_hz": [60, 500], "character": "tonal", "onset": False},
    "voice": {"nominal_hz": [400, 2000], "search_hz": [250, 4000], "character": "sustained", "onset": False},
    "snare": {"nominal_hz": [2000, 6000], "search_hz": [1000, 8000], "character": "transient", "onset": True},
    "hats": {"nominal_hz": [6000, 16000], "search_hz": [4000, 18000], "character": "transient", "onset": True},
}

CHARACTERS = ("transient", "tonal", "sustained")


@dataclass(frozen=True)
class TrackerSpec:
    name: str
    nominal_hz: tuple[float, float]
    search_hz: tuple[float, float]
    character: str = "tonal"
    onset: bool = False
    label: str = ""

    def __post_init__(self):
        if self.character not in CHARACTERS:
            raise ValueError(f"{self.name}: character debe ser uno de {CHARACTERS}")
        lo, hi = self.nominal_hz
        slo, shi = self.search_hz
        if not (0 < slo <= lo < hi <= shi):
            raise ValueError(f"{self.name}: nominal_hz debe estar dentro de search_hz")

    @property
    def transient(self) -> bool:
        return self.character == "transient"


@dataclass(frozen=True)
class AnalyzerConfig:
    trackers: tuple[TrackerSpec, ...]
    sample_rate: int = 48000
    fft_size: int = 2048
    hop_size: int = 512
    # adaptation
    template_time_constant_s: float = 4.0
    center_max_shift_per_s: float = 0.05
    hysteresis: float = 0.15
    min_confidence: float = 0.3
    # smoothing (0 = sin suavizar, 1 = congelado)
    attack: float = 0.2
    release: float = 0.85
    # separation
    hpss_frames: int = 9
    nmf_iterations: int = 8
    prior_pull_s: float = 30.0
    silence_db: float = -65.0
    # onsets
    onset_threshold_k: float = 1.5
    onset_relative_min: float = 0.2
    onset_min_interval_s: float = 0.08
    onset_min_percussive_share: float = 0.3
    # tempo
    bpm_range: tuple[float, float] = (70.0, 180.0)
    prior_bpm: float = 120.0
    tempo_window_s: float = 8.0
    tempo_update_s: float = 0.5

    extra: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def names(self) -> list[str]:
        return [t.name for t in self.trackers]

    def tracker(self, name: str) -> TrackerSpec:
        return next(t for t in self.trackers if t.name == name)

    @classmethod
    def from_dict(cls, d: dict) -> "AnalyzerConfig":
        d = d or {}
        trackers = tuple(
            TrackerSpec(
                name=name,
                nominal_hz=tuple(float(x) for x in t["nominal_hz"]),
                search_hz=tuple(float(x) for x in t.get("search_hz", t["nominal_hz"])),
                character=t.get("character", "tonal"),
                onset=bool(t.get("onset", False)),
                label=t.get("label", ""),
            )
            for name, t in (d.get("trackers") or _DEFAULT_TRACKERS).items()
        )
        ad = d.get("adaptation", {}) or {}
        sm = d.get("smoothing", {}) or {}
        sp = d.get("separation", {}) or {}
        on = d.get("onsets", {}) or {}
        tp = d.get("tempo", {}) or {}
        kw = dict(
            trackers=trackers,
            sample_rate=d.get("sample_rate"),
            fft_size=d.get("fft_size"),
            hop_size=d.get("hop_size"),
            template_time_constant_s=ad.get("template_time_constant_s"),
            center_max_shift_per_s=ad.get("center_max_shift_per_s"),
            hysteresis=ad.get("hysteresis"),
            min_confidence=ad.get("min_confidence"),
            attack=sm.get("attack"),
            release=sm.get("release"),
            hpss_frames=sp.get("hpss_frames"),
            nmf_iterations=sp.get("nmf_iterations"),
            prior_pull_s=sp.get("prior_pull_s"),
            silence_db=sp.get("silence_db"),
            onset_threshold_k=on.get("threshold_k"),
            onset_relative_min=on.get("relative_min"),
            onset_min_interval_s=on.get("min_interval_s"),
            onset_min_percussive_share=on.get("min_percussive_share"),
            bpm_range=tuple(tp["bpm_range"]) if "bpm_range" in tp else None,
            prior_bpm=tp.get("prior_bpm"),
            tempo_window_s=tp.get("window_s"),
            tempo_update_s=tp.get("update_s"),
        )
        return cls(**{k: v for k, v in kw.items() if v is not None}, extra=d)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "AnalyzerConfig":
        p = Path(path) if path else DEFAULT_PATH
        if not p.exists():
            if path:
                raise FileNotFoundError(p)
            return cls.from_dict({})
        return cls.from_dict(yaml.safe_load(p.read_text()) or {})
