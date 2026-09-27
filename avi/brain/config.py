"""Configuracion del show (config/show.yaml) para el cerebro: paletas, escenas,
mapeo instrumento -> intencion y umbrales del detector de secciones."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SECTIONS = ("calm", "build", "drop", "break")

# Copia minima de config/show.example.yaml por si el paquete se instala sin config/.
_DEFAULT_SHOW = {
    "mapping": {
        "sub": {"lights": {"all": "dimmer_base"}, "td": "scale_slow"},
        "kick": {"lights": {"front": "dimmer_flash"}, "td": "zoom_pulse"},
        "bass": {"lights": {"all": "hue_shift"}, "td": "noise_amp"},
        "voice": {"lights": {"all": "white"}, "td": "brightness"},
        "snare": {"lights": {"all": "strobe"}, "td": "glitch", "only_sections": ["drop"]},
        "hats": {"lights": {"wave": "chase"}, "td": "sparkle_rate"},
    },
    "palettes": {
        "frio": [[0.1, 0.3, 1.0], [0.0, 0.8, 0.9], [0.6, 0.6, 1.0]],
        "fuego": [[1.0, 0.2, 0.0], [1.0, 0.6, 0.0], [1.0, 1.0, 0.8]],
        "neon": [[1.0, 0.1, 0.4], [0.1, 0.3, 1.0], [1.0, 1.0, 1.0]],
    },
    "scenes": [
        {"id": 0, "name": "ambiente", "td_scene": 0, "td_clip": 1, "palettes": ["frio"], "sections": ["calm", "break"]},
        {"id": 1, "name": "subida", "td_scene": 1, "td_clip": 2, "palettes": ["frio", "neon"], "sections": ["build"]},
        {"id": 2, "name": "drop", "td_scene": 2, "td_clip": 3, "palettes": ["fuego", "neon"], "sections": ["drop"]},
    ],
    "rules": {"phrase_beats": 16, "min_scene_bars": 8, "section_hysteresis_bars": 2},
}


@dataclass(frozen=True)
class Scene:
    id: int
    name: str
    td_scene: int
    td_clip: int
    palettes: tuple[str, ...]
    sections: tuple[str, ...]


@dataclass(frozen=True)
class SectionRules:
    """Umbrales del detector (por compas). Ver docs/F2_CEREBRO.md."""
    kick_hits_present: int = 2        # golpes de bombo por compas para decir "hay bombo"
    kick_hits_dense: int = 3          # ... para decir "bombo denso" (drop)
    drop_db_from_peak: float = 4.0    # el drop suena a <= 4 dB del compas mas fuerte reciente
    drop_hold_db: float = 8.0         # ... y se suelta si cae mas de 8 dB
    drop_jump_db: float = 3.0         # salto de volumen vs los 4 compases previos = drop inmediato
    build_bars: int = 4               # ventana para medir la subida
    build_density_slope: float = 0.5  # golpes de hats+snare por compas que suma cada compas
    build_density_rel: float = 0.12   # ... y relativo a la media de la ventana (ignora ruido)
    build_max_flat_bars: int = 16     # un build que ya no sube se suelta a los 16 compases
    build_db_slope: float = 0.6       # dB por compas que sube el volumen
    build_min_hits: int = 2           # golpes de hats+snare minimos en el compas
    default_bpm: float = 120.0        # reloj propio cuando el analisis aun no tiene tempo


@dataclass(frozen=True)
class ShowConfig:
    palettes: dict[str, tuple[tuple[float, float, float], ...]]
    scenes: tuple[Scene, ...]
    mapping: dict[str, dict]
    phrase_beats: int = 16
    min_scene_bars: int = 8
    section_hysteresis_bars: int = 2
    palette_fade_beats: float = 4.0   # cruce de paleta; el drop entra en seco
    section_gain: dict[str, float] = field(default_factory=lambda: {
        "calm": 0.6, "build": 0.75, "drop": 1.0, "break": 0.35})
    strobe_sections: tuple[str, ...] = ("drop",)
    sections: SectionRules = SectionRules()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "ShowConfig":
        candidates = [Path(path)] if path else [ROOT / "config" / "show.yaml", ROOT / "config" / "show.example.yaml"]
        for p in candidates:
            if p.exists():
                return cls.from_dict(yaml.safe_load(p.read_text()) or {})
        if path:
            raise FileNotFoundError(path)
        return cls.from_dict(_DEFAULT_SHOW)

    @classmethod
    def from_dict(cls, d: dict) -> "ShowConfig":
        d = {**_DEFAULT_SHOW, **{k: v for k, v in d.items() if v}}
        palettes = {name: tuple(tuple(float(x) for x in c) for c in cols) for name, cols in d["palettes"].items()}
        for name, cols in palettes.items():
            if len(cols) != 3 or any(len(c) != 3 or not all(0 <= x <= 1 for x in c) for c in cols):
                raise ValueError(f"paleta {name}: deben ser 3 colores RGB 0-1")
        scenes = []
        for i, s in enumerate(d["scenes"]):
            sc = Scene(
                id=int(s.get("id", i)), name=s.get("name", f"escena {i}"),
                td_scene=int(s.get("td_scene", i)), td_clip=int(s.get("td_clip", 0)),
                palettes=tuple(s.get("palettes") or list(palettes)[:1]),
                sections=tuple(s.get("sections") or ()),
            )
            bad = [p for p in sc.palettes if p not in palettes] + [x for x in sc.sections if x not in SECTIONS]
            if bad:
                raise ValueError(f"escena {sc.name}: desconocido {bad}")
            scenes.append(sc)
        if not scenes:
            raise ValueError("hace falta al menos una escena")
        rules = {**_DEFAULT_SHOW["rules"], **(d.get("rules") or {})}
        sec = dict(rules.pop("sections", None) or {})
        known = {k: rules.pop(k) for k in ("palette_fade_beats", "section_gain", "strobe_sections") if k in rules}
        if "section_gain" in known:
            known["section_gain"] = {**cls.__dataclass_fields__["section_gain"].default_factory(), **known["section_gain"]}
        if "strobe_sections" in known:
            known["strobe_sections"] = tuple(known["strobe_sections"])
        return cls(
            palettes=palettes, scenes=tuple(scenes), mapping=d["mapping"],
            phrase_beats=int(rules.get("phrase_beats", 16)),
            min_scene_bars=int(rules.get("min_scene_bars", 8)),
            section_hysteresis_bars=int(rules.get("section_hysteresis_bars", 2)),
            sections=SectionRules(**sec), **known,
        )

    def scene(self, scene_id: int) -> Scene:
        for s in self.scenes:
            if s.id == scene_id:
                return s
        raise KeyError(scene_id)

    def scenes_for(self, section: str) -> list[Scene]:
        return [s for s in self.scenes if section in s.sections] or list(self.scenes[:1])

    @property
    def groups(self) -> list[str]:
        out: list[str] = []
        for m in self.mapping.values():
            for g in (m.get("lights") or {}):
                if g not in out:
                    out.append(g)
        return out
