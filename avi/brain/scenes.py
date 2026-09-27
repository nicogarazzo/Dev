"""Motor de escenas (el "DJ de luces"): seccion -> escena + paleta, con reglas anti-caos.

1. Cambios cuantizados al inicio de frase (16 beats), salvo el drop: entra en el beat 1.
2. Duracion minima por escena (8 compases); el drop se la salta, es el momento clave.
3. El override (controlador MIDI, F5) siempre gana hasta que se suelta.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import Scene, ShowConfig

RGB = tuple[float, float, float]


@dataclass
class Override:
    scene: int | None = None
    palette: str | None = None
    blackout: bool = False

    @property
    def active(self) -> bool:
        return self.scene is not None or self.palette is not None or self.blackout

    def to_dict(self) -> dict | None:
        if not self.active:
            return None
        return {"scene": self.scene, "palette": self.palette, "blackout": self.blackout}


class PaletteMixer:
    """Paleta vigente con cruce suave (en segundos) hacia la nueva."""

    def __init__(self, colors: tuple[RGB, ...]):
        self.src = self.dst = tuple(tuple(c) for c in colors)
        self.t0 = 0.0
        self.dur = 0.0

    def go(self, colors: tuple[RGB, ...], t: float, dur_s: float) -> None:
        self.src = self.current(t)
        self.dst = tuple(tuple(c) for c in colors)
        self.t0, self.dur = t, max(0.0, dur_s)

    def current(self, t: float) -> tuple[RGB, ...]:
        if self.dur <= 0 or t >= self.t0 + self.dur:
            return self.dst
        a = max(0.0, (t - self.t0) / self.dur)
        return tuple(tuple(s + (d - s) * a for s, d in zip(cs, cd)) for cs, cd in zip(self.src, self.dst))


class SceneEngine:
    def __init__(self, cfg: ShowConfig):
        self.cfg = cfg
        first = cfg.scenes_for("calm")[0]
        self.scene: Scene = first
        self.palette_name = first.palettes[0]
        self.mixer = PaletteMixer(cfg.palettes[self.palette_name])
        self.bars_in_scene = 0
        self.pending: Scene | None = None
        self.override = Override()
        self._auto_scene = first
        self._auto_palette = self.palette_name
        self._rotation: dict = {}
        self.changes: list[dict] = []   # historial para el timeline / UI

    # --- automatico -------------------------------------------------------------
    def on_bar(self, section: str, phrase_start: bool, t: float, beat_s: float) -> None:
        """Llamar en cada downbeat, despues de actualizar la seccion."""
        self.bars_in_scene += 1
        if section not in self._auto_scene.sections:
            if self.pending is None or section not in self.pending.sections:
                self.pending = self._pick_scene(section)
        else:
            self.pending = None
        if self.pending is None:
            return
        is_drop = section == "drop"
        if is_drop or (phrase_start and self.bars_in_scene >= self.cfg.min_scene_bars):
            self._switch(self.pending, t, 0.0 if is_drop else self.cfg.palette_fade_beats * beat_s, section)
            self.pending = None

    def _pick_scene(self, section: str) -> Scene:
        options = self.cfg.scenes_for(section)
        others = [s for s in options if s.id != self._auto_scene.id] or options
        k = self._rotation.get(f"section:{section}", 0)
        self._rotation[f"section:{section}"] = k + 1
        return others[k % len(others)]

    def _pick_palette(self, scene: Scene) -> str:
        opts = [p for p in scene.palettes if p != self._auto_palette] or list(scene.palettes)
        k = self._rotation.get(scene.id, 0)
        self._rotation[scene.id] = k + 1
        return opts[k % len(opts)]

    def _switch(self, scene: Scene, t: float, fade_s: float, section: str) -> None:
        self._auto_scene = scene
        self._auto_palette = self._pick_palette(scene)
        self.bars_in_scene = 0
        self.changes.append({"t": round(t, 3), "section": section, "scene": scene.id,
                             "scene_name": scene.name, "palette": self._auto_palette})
        self._apply(t, fade_s)

    # --- override ---------------------------------------------------------------
    def set_override(self, t: float, scene: int | None = None, palette: str | None = None,
                     blackout: bool | None = None) -> None:
        if scene is not None:
            self.cfg.scene(scene)            # KeyError si no existe
            self.override.scene = scene
        if palette is not None:
            if palette not in self.cfg.palettes:
                raise KeyError(palette)
            self.override.palette = palette
        if blackout is not None:
            self.override.blackout = blackout
        self._apply(t, 0.0)

    def release(self, t: float, beat_s: float = 0.5) -> None:
        """Suelta el override: vuelve a lo que el cerebro eligio mientras tanto."""
        self.override = Override()
        self._apply(t, self.cfg.palette_fade_beats * beat_s)

    def _apply(self, t: float, fade_s: float) -> None:
        o = self.override
        self.scene = self.cfg.scene(o.scene) if o.scene is not None else self._auto_scene
        if o.palette is not None:
            name = o.palette
        elif o.scene is not None and self._auto_palette not in self.scene.palettes:
            name = self.scene.palettes[0]
        else:
            name = self._auto_palette
        if name != self.palette_name or fade_s == 0:
            self.palette_name = name
            self.mixer.go(self.cfg.palettes[name], t, fade_s)

    def palette(self, t: float) -> tuple[RGB, ...]:
        return self.mixer.current(t)
