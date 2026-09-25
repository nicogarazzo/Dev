"""Rastreadores adaptativos por instrumento.

Cada rastreador parte de un rango nominal dentro de un rango de busqueda, guarda una
huella espectral (la forma del espectro cuando su instrumento domina) y la actualiza
continuamente. En cada espectro, la energia de cada bin se reparte entre los
rastreadores en proporcion a sus huellas (mascara suave), asi bombo y bajo dejan de
contaminarse aunque compartan frecuencias. Ver docs/PLAN_MVP.md, seccion 4.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

EPS = 1e-12


@dataclass
class TrackerConfig:
    name: str
    nominal_hz: tuple[float, float]
    search_hz: tuple[float, float]
    character: str = "tonal"          # transient | tonal | sustained
    onset: bool = False
    label: str = ""

    @property
    def is_transient(self) -> bool:
        return self.character == "transient"


@dataclass
class AdaptationConfig:
    template_time_constant_s: float = 4.0
    center_max_shift_per_s: float = 0.05
    hysteresis: float = 0.15
    min_confidence: float = 0.3
    mask: str = "wiener"
    level_reference_decay_s: float = 6.0   # cuanto tarda la referencia de nivel en bajar
    onset_min_interval_s: float = 0.12
    onset_threshold: float = 2.0           # flujo > media * umbral => golpe
    smoothing_attack: float = 0.2
    smoothing_release: float = 0.85


@dataclass
class TrackerState:
    """Lo que un rastreador expone hacia afuera (va al ShowState)."""
    name: str
    level: float = 0.0
    raw: float = 0.0
    onset: bool = False
    hz: tuple[float, float] = (0.0, 0.0)
    confidence: float = 0.0

    def as_dict(self) -> dict:
        return {
            "level": round(float(self.level), 4),
            "onset": bool(self.onset),
            "hz": [round(float(self.hz[0]), 1), round(float(self.hz[1]), 1)],
            "confidence": round(float(self.confidence), 3),
        }


def _bump(freqs: np.ndarray, low: float, high: float) -> np.ndarray:
    """Huella inicial: una campana suave sobre [low, high]."""
    center = 0.5 * (low + high)
    half = max(0.5 * (high - low), 1.0)
    x = (freqs - center) / half
    out = np.zeros_like(freqs, dtype=np.float64)
    inside = np.abs(x) <= 1.0
    out[inside] = 0.5 * (1.0 + np.cos(np.pi * x[inside]))
    return out


class InstrumentTracker:
    def __init__(self, cfg: TrackerConfig, freqs: np.ndarray, frame_rate: float, adapt: AdaptationConfig):
        self.cfg = cfg
        self.freqs = freqs
        self.frame_rate = frame_rate
        self.adapt = adapt
        self.search_idx = np.where((freqs >= cfg.search_hz[0]) & (freqs <= cfg.search_hz[1]))[0]
        if len(self.search_idx) == 0:
            raise ValueError(f"{cfg.name}: el rango de busqueda {cfg.search_hz} no cubre ningun bin")
        self.search_mask = np.zeros_like(freqs, dtype=bool)
        self.search_mask[self.search_idx] = True
        self.nominal_template = _bump(freqs, *cfg.nominal_hz) * self.search_mask
        if self.nominal_template.max() <= 0:  # rango nominal demasiado angosto para la FFT
            self.nominal_template = self.search_mask.astype(np.float64)
        self.template = self.nominal_template.copy()
        dt = 1.0 / frame_rate
        self._alpha_template = 1.0 - np.exp(-dt / max(adapt.template_time_constant_s, dt))
        self._ref_decay = np.exp(-dt / max(adapt.level_reference_decay_s, dt))
        self._flux_decay = np.exp(-dt / 1.0)
        self._ref = 1e-6
        self._prev_masked = np.zeros_like(freqs, dtype=np.float64)
        self._prev_power = np.zeros_like(freqs, dtype=np.float64)
        self._last_power = np.zeros_like(freqs, dtype=np.float64)
        self._flux_mean = 0.0
        self._prev_energy = 0.0
        self._flux_peak = 0.0
        self._peak_decay = np.exp(-dt / 0.25)
        self._last_onset_frame = -10**9
        self._low_conf_frames = 0
        self._frame = 0
        self.state = TrackerState(name=cfg.name, hz=cfg.nominal_hz, confidence=1.0)

    # ----- mascara -----
    def weight(self) -> np.ndarray:
        """Peso por bin para el reparto de energia (huella normalizada a maximo 1)."""
        m = self.template.max()
        return self.template / m if m > 0 else self.template

    # ----- procesamiento de un espectro -----
    def process(self, power: np.ndarray, mask: np.ndarray, learn_ok: bool = True, total_power: float | None = None) -> TrackerState:
        """learn_ok=False: hubo un golpe hace poco; los tonales no aprenden de este frame."""
        self._frame += 1
        self._last_power = power
        masked = power * mask
        energy = float(masked[self.search_idx].sum())
        raw = np.sqrt(energy)

        # Referencia de nivel adaptativa: sube al instante, baja despacio.
        self._ref = max(raw, self._ref * self._ref_decay, 1e-6)
        level_inst = min(1.0, raw / self._ref) if self._ref > 1e-6 else 0.0
        prev = self.state.level
        a = self.adapt.smoothing_attack if level_inst > prev else self.adapt.smoothing_release
        level = a * prev + (1.0 - a) * level_inst

        # Onset: flujo espectral positivo del espectro CRUDO en el rango de busqueda
        # (independiente de como se reparta la mascara), aceptado solo si el rastreador
        # se queda con una parte importante de esa energia.
        raw_band = power[self.search_idx]
        flux = float(np.maximum(raw_band - self._prev_power[self.search_idx], 0.0).sum())
        energy_raw = float(raw_band.sum())
        share = energy / energy_raw if energy_raw > 0 else 0.0
        self._prev_masked = masked
        onset = False
        self._flux_peak *= self._peak_decay
        if self.cfg.onset:
            thr = max(self.adapt.onset_threshold * self._flux_mean, 0.3 * self._flux_peak)
            min_gap = int(self.adapt.onset_min_interval_s * self.frame_rate)
            if (
                flux > thr
                and flux > 0.7 * self._prev_energy       # la energia de la banda casi se duplica
                and energy_raw > 0.002 * (total_power if total_power is not None else energy_raw)  # no es un golpe si la banda esta casi muda
                and share > 0.3
                and self._frame - self._last_onset_frame >= min_gap
            ):
                onset = True
                self._last_onset_frame = self._frame
                self._flux_peak = max(self._flux_peak, flux)
        self._flux_mean = self._flux_decay * self._flux_mean + (1.0 - self._flux_decay) * flux
        self._prev_energy = energy_raw

        # Actualizacion de la huella: en los golpes (transitorios) o cuando esta activo (tonales).
        active = raw > 0.35 * self._ref
        if self.cfg.is_transient:
            if onset:
                # Lo nuevo en este frame: el golpe. Lo estable (bajo, voz) se cancela.
                novelty = np.maximum(power - self._prev_power, 0.0)
                self._learn(novelty, rate=min(1.0, self._alpha_template * self.frame_rate * 0.5))
        elif active and learn_ok:
            self._learn(power, rate=self._alpha_template)
        self._prev_power = power

        # Rango actual y confianza.
        hz, confidence = self._describe(masked)
        if confidence < self.adapt.min_confidence and level > 0.2:
            self._low_conf_frames += 1
        else:
            self._low_conf_frames = 0
        if self._low_conf_frames > 2 * self.frame_rate:  # 2 s perdido -> vuelve al nominal
            self.template = self.nominal_template.copy()
            self._low_conf_frames = 0
            hz = self.cfg.nominal_hz

        self.state = TrackerState(self.cfg.name, level, raw, onset, hz, confidence)
        return self.state

    def _learn(self, power: np.ndarray, rate: float) -> None:
        shape = power * self.search_mask
        peak = shape.max()
        if peak <= 0:
            return
        shape = shape / peak
        # Suaviza la forma (3 bins) para que la huella no sea una linea.
        shape = np.convolve(shape, np.ones(3) / 3.0, mode="same") * self.search_mask
        new = (1.0 - rate) * self.template + rate * shape
        # Histeresis: solo se mueve si el cambio es apreciable.
        if np.abs(new - self.template).max() >= self.adapt.hysteresis * rate:
            self.template = new

    def _describe(self, masked: np.ndarray) -> tuple[tuple[float, float], float]:
        w = self.template[self.search_idx]
        f = self.freqs[self.search_idx]
        total = w.sum()
        if total <= 0:
            return self.cfg.nominal_hz, 0.0
        centroid = float((w * f).sum() / total)
        spread = float(np.sqrt(((f - centroid) ** 2 * w).sum() / total))
        low = max(self.cfg.search_hz[0], centroid - 1.5 * spread)
        high = min(self.cfg.search_hz[1], centroid + 1.5 * spread)
        if high - low < 5.0:
            high = min(self.cfg.search_hz[1], low + 5.0)
        # Confianza: que parte de lo que suena en su banda es suyo (dominancia).
        in_band = (f >= low) & (f <= high)
        own = float(masked[self.search_idx][in_band].sum())
        total = float(self._last_power[self.search_idx][in_band].sum())
        conf = own / total if total > 0 else 1.0
        return (low, high), float(min(1.0, conf))


class TrackerBank:
    """Todos los rastreadores compartiendo el mismo espectro con mascara suave."""

    def __init__(self, configs: list[TrackerConfig], freqs: np.ndarray, frame_rate: float, adapt: AdaptationConfig | None = None):
        self.adapt = adapt or AdaptationConfig()
        self.trackers = [InstrumentTracker(c, freqs, frame_rate, self.adapt) for c in configs]
        self.freqs = freqs
        self._quiet_frames = int(0.15 * frame_rate)   # tras un golpe, los tonales no aprenden
        self._since_onset = 10**9

    @property
    def names(self) -> list[str]:
        return [t.cfg.name for t in self.trackers]

    def process(self, power: np.ndarray) -> dict[str, TrackerState]:
        power = np.asarray(power, dtype=np.float64)
        weights = np.stack([t.weight() for t in self.trackers])   # (n, bins)
        if self.adapt.mask == "wiener":
            # Huella al cuadrado: el que mas "espera" un bin se lo lleva casi entero.
            weights = weights ** 2
        denom = weights.sum(axis=0) + EPS
        masks = weights / denom
        learn_ok = self._since_onset > self._quiet_frames
        total_power = float(power.sum())
        out = {}
        any_onset = False
        for tracker, mask in zip(self.trackers, masks):
            out[tracker.cfg.name] = tracker.process(power, mask, learn_ok=learn_ok, total_power=total_power)
            any_onset = any_onset or out[tracker.cfg.name].onset
        self._since_onset = 0 if any_onset else self._since_onset + 1
        return out

    def states(self) -> dict[str, dict]:
        return {t.cfg.name: t.state.as_dict() for t in self.trackers}


def configs_from_yaml(cfg: dict) -> tuple[list[TrackerConfig], AdaptationConfig]:
    trackers = []
    for name, spec in (cfg.get("trackers") or {}).items():
        trackers.append(
            TrackerConfig(
                name=name,
                nominal_hz=tuple(spec["nominal_hz"]),
                search_hz=tuple(spec.get("search_hz", spec["nominal_hz"])),
                character=spec.get("character", "tonal"),
                onset=bool(spec.get("onset", False)),
                label=spec.get("label", name),
            )
        )
    a = cfg.get("adaptation") or {}
    s = cfg.get("smoothing") or {}
    adapt = AdaptationConfig(
        template_time_constant_s=float(a.get("template_time_constant_s", 4.0)),
        center_max_shift_per_s=float(a.get("center_max_shift_per_s", 0.05)),
        hysteresis=float(a.get("hysteresis", 0.15)),
        min_confidence=float(a.get("min_confidence", 0.3)),
        mask=str(a.get("mask", "wiener")),
        smoothing_attack=float(s.get("attack", 0.2)),
        smoothing_release=float(s.get("release", 0.85)),
    )
    return trackers, adapt
