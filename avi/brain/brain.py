"""El cerebro: AudioFrame (F1) -> ShowState, el unico estado que leen luces y visuales.

    brain = Brain()                       # config/show.yaml (o el ejemplo)
    for frame in analyzer.process(block):
        state = brain.update(frame)       # state.section, state.scene, state.palette...
        osc.send(state.to_dict())         # F3: DMX y OSC solo traducen esto

Override (controlador MIDI, F5): brain.set_override(scene=2) / brain.release().
"""
from __future__ import annotations

from dataclasses import dataclass, field

from avi.audio import AudioFrame

from .config import ShowConfig
from .intents import IntentEngine
from .scenes import SceneEngine
from .sections import BarClock, SectionDetector


@dataclass
class ShowState:
    frame: AudioFrame
    section: str
    section_bars: int            # compases que lleva la seccion
    scene: int
    scene_name: str
    td_scene: int
    td_clip: int
    palette: list[list[float]]   # 3 colores RGB 0-1, ya con el cruce aplicado
    palette_name: str
    lights: dict[str, dict]      # grupo -> {dimmer, rgb, white, strobe, chase, chase_step}
    visuals: dict[str, float]    # parametro de TD -> 0..1
    override: dict | None = None
    bar_start: bool = False
    phrase_start: bool = False
    changes: list[str] = field(default_factory=list)   # "section", "scene", "palette" en este frame

    @property
    def t(self) -> float:
        return self.frame.t

    @property
    def instruments(self):
        return self.frame.instruments

    def to_dict(self) -> dict:
        """El ShowState del plan (§3): todo lo del AudioFrame + lo que decide el cerebro."""
        d = self.frame.to_dict()
        d.update({
            "section": self.section,
            "section_bars": self.section_bars,
            "scene": self.scene,
            "scene_name": self.scene_name,
            "td_scene": self.td_scene,
            "td_clip": self.td_clip,
            "palette": [[round(c, 4) for c in col] for col in self.palette],
            "palette_name": self.palette_name,
            "lights": self.lights,
            "visuals": self.visuals,
            "override": self.override,
        })
        if self.changes:
            d["changes"] = self.changes
        return d


class Brain:
    def __init__(self, cfg: ShowConfig | None = None):
        self.cfg = cfg or ShowConfig.load()
        self.clock = BarClock(self.cfg.sections.default_bpm, self.cfg.phrase_beats)
        self.sections = SectionDetector(self.cfg.sections, self.cfg.section_hysteresis_bars)
        self.scenes = SceneEngine(self.cfg)
        self.intents = IntentEngine(self.cfg)
        self.t = 0.0
        self._pending_changes: list[str] = []

    @property
    def beat_s(self) -> float:
        return self.clock.period

    def update(self, f: AudioFrame) -> ShowState:
        self.t = f.t
        prev_section, prev_scene, prev_pal = self.sections.section, self.scenes.scene.id, self.scenes.palette_name
        _, downbeat = self.clock.push(f)
        if downbeat:
            # el compas que termina se cierra antes de sumar el primer frame del nuevo
            section = self.sections.close_bar(4 * self.beat_s)
            self.scenes.on_bar(section, self.clock.phrase_start, f.t, self.beat_s)
        self.sections.push(f)

        sc = self.scenes.scene
        palette = self.scenes.palette(f.t)
        lights, visuals = self.intents.update(
            f, self.sections.section, palette, self.sections.build_progress, self.scenes.override.blackout)
        changes = self._pending_changes
        self._pending_changes = []
        if self.sections.section != prev_section:
            changes.append("section")
        if sc.id != prev_scene:
            changes.append("scene")
        if self.scenes.palette_name != prev_pal:
            changes.append("palette")
        return ShowState(
            frame=f, section=self.sections.section, section_bars=self.sections.bars_in_section,
            scene=sc.id, scene_name=sc.name, td_scene=sc.td_scene, td_clip=sc.td_clip,
            palette=[list(c) for c in palette], palette_name=self.scenes.palette_name,
            lights=lights, visuals=visuals, override=self.scenes.override.to_dict(),
            bar_start=downbeat, phrase_start=downbeat and self.clock.phrase_start, changes=changes,
        )

    # --- override (F5 lo conecta al controlador MIDI) ----------------------------
    def set_override(self, scene: int | None = None, palette: str | None = None,
                     blackout: bool | None = None) -> None:
        before = (self.scenes.scene.id, self.scenes.palette_name)
        self.scenes.set_override(self.t, scene=scene, palette=palette, blackout=blackout)
        self._note(before)

    def release(self) -> None:
        before = (self.scenes.scene.id, self.scenes.palette_name)
        self.scenes.release(self.t, self.beat_s)
        self._note(before)

    def _note(self, before) -> None:
        if self.scenes.scene.id != before[0]:
            self._pending_changes.append("scene")
        if self.scenes.palette_name != before[1]:
            self._pending_changes.append("palette")


def run_brain(frames, cfg: ShowConfig | None = None) -> list[ShowState]:
    brain = Brain(cfg)
    return [brain.update(f) for f in frames]


def section_spans(states: list[ShowState]) -> list[dict]:
    """[{name, start, end, scene, palette}] por tramo de seccion (formato que usa la UI)."""
    spans: list[dict] = []
    for s in states:
        if not spans or spans[-1]["name"] != s.section:
            if spans:
                spans[-1]["end"] = round(s.t, 3)
            spans.append({"name": s.section, "start": round(s.t, 3), "end": round(s.t, 3)})
    if spans:
        spans[-1]["end"] = round(states[-1].t, 3)
    return spans
