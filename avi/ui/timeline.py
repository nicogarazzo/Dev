"""Timeline para la UI: analisis (avi.audio) + espectro, reducido a ~30 cuadros/s.

La UI lo reproduce sincronizado con el audio (modo demo y archivo), y el mismo
formato de cuadro viaja por SSE en vivo.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import yaml

from avi.audio import Analyzer, AnalyzerConfig, AudioFrame

from .spectrum import SpectrumTap

ROOT = Path(__file__).resolve().parents[2]


def frame_payload(frame: AudioFrame, spectrum: np.ndarray | None) -> dict:
    """Un cuadro para la UI: lo del analizador + el espectro en enteros 0..99."""
    d = frame.to_dict()
    if spectrum is not None:
        d["spectrum"] = [int(v * 99) for v in spectrum]
    return d


def merge_payloads(group: list[dict]) -> dict:
    """Une varios cuadros en uno: niveles y espectro = maximo, golpes y beats = cualquiera."""
    out = dict(group[-1])
    out["is_beat"] = any(g["is_beat"] for g in group)
    out["instruments"] = {}
    for name in group[-1]["instruments"]:
        last = dict(group[-1]["instruments"][name])
        last["level"] = max(g["instruments"][name]["level"] for g in group)
        last["onset"] = any(g["instruments"][name]["onset"] for g in group)
        out["instruments"][name] = last
    if "spectrum" in group[-1]:
        out["spectrum"] = [max(vals) for vals in zip(*(g["spectrum"] for g in group))]
    return out


def load_show(path: Path | None = None) -> dict:
    """Mapeo, paletas y escenas; config/show.yaml si existe, si no el ejemplo."""
    for p in ([path] if path else []) + [ROOT / "config" / "show.yaml", ROOT / "config" / "show.example.yaml"]:
        if p and p.exists():
            return yaml.safe_load(p.read_text()) or {}
    return {}


def load_fixtures(path: Path | None = None) -> dict:
    for p in ([path] if path else []) + [ROOT / "config" / "fixtures.yaml", ROOT / "config" / "fixtures.example.yaml"]:
        if p and p.exists():
            return yaml.safe_load(p.read_text()) or {}
    return {}


def meta(cfg: AnalyzerConfig, tap: SpectrumTap, mode: str, title: str = "") -> dict:
    show = load_show()
    fixtures = load_fixtures()
    return {
        "mode": mode,
        "title": title,
        "trackers": [
            {"name": t.name, "label": t.label or t.name, "nominal_hz": list(t.nominal_hz),
             "search_hz": list(t.search_hz), "character": t.character, "onset": t.onset}
            for t in cfg.trackers
        ],
        "spectrum_hz": [int(round(c)) for c in tap.centers],
        "mapping": show.get("mapping", {}),
        "palettes": show.get("palettes", {}),
        "fixtures": [
            {"name": f["name"], "address": f.get("address"), "profile": f.get("profile")}
            for f in fixtures.get("fixtures", [])
        ],
        "groups": fixtures.get("groups", {}),
    }


def build_timeline(samples: np.ndarray, sample_rate: int, cfg: AnalyzerConfig | None = None,
                   fps: float = 30.0, mode: str = "demo", title: str = "") -> dict:
    """Analiza una senal completa y devuelve {meta, fps, duration, frames}."""
    cfg = cfg or AnalyzerConfig.load()
    an = Analyzer(cfg, sample_rate)
    tap = SpectrumTap(sample_rate, cfg.fft_size, cfg.hop_size)
    groups: dict[int, list[dict]] = {}
    block = 4096
    for i in range(0, len(samples), block):
        chunk = samples[i:i + block]
        frames = an.process(chunk)
        specs = tap.push(chunk)
        for fr, sp in zip(frames, specs):
            groups.setdefault(int(fr.t * fps), []).append(frame_payload(fr, sp))
    frames_out = [merge_payloads(groups[k]) for k in sorted(groups)]
    return {
        "meta": meta(cfg, tap, mode, title),
        "fps": fps,
        "duration": round(len(samples) / sample_rate, 3),
        "frames": frames_out,
    }
