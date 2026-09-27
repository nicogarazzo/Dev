"""Intenciones: instrumentos + seccion + paleta -> que hace cada grupo de luces y
cada parametro de TouchDesigner.

El cerebro nunca habla de canales DMX: dice "grupo front, dimmer 0.9, color X".
La capa de patch (F3) lo traduce a canales y aplica los delays de cada grupo.

Intenciones de luces (config/show.yaml -> mapping.<instrumento>.lights):
    dimmer_base   nivel del instrumento como dimmer de fondo (respira)
    dimmer_flash  flash que salta a 1 en cada golpe y cae en ~150 ms
    hue_shift     mueve el color del grupo del color 1 al 2 de la paleta
    white         canal blanco
    strobe        strobe corto en cada golpe (solo en las secciones permitidas)
    chase         cada golpe avanza un paso del chase (F3 lo reparte con delay)
"""
from __future__ import annotations

import math

from avi.audio import AudioFrame

from .config import ShowConfig

LIGHT_INTENTS = ("dimmer_base", "dimmer_flash", "hue_shift", "white", "strobe", "chase")
FLASH_TAU_S = 0.15
STROBE_TAU_S = 0.05
ONSET_TAU_S = 0.2


def _lerp(a, b, x):
    return tuple(ai + (bi - ai) * x for ai, bi in zip(a, b))


class IntentEngine:
    def __init__(self, cfg: ShowConfig):
        self.cfg = cfg
        self.groups = cfg.groups
        self.env: dict[str, float] = {}         # envolvente de golpe por instrumento
        self.chase_step: dict[str, int] = {g: 0 for g in self.groups}
        self.last_t: float | None = None
        for name, m in cfg.mapping.items():
            for g, intent in (m.get("lights") or {}).items():
                if intent not in LIGHT_INTENTS:
                    raise ValueError(f"mapping.{name}: intencion desconocida {intent!r} (validas: {LIGHT_INTENTS})")

    def _allowed(self, m: dict, section: str) -> bool:
        only = m.get("only_sections")
        return not only or section in only

    def update(self, f: AudioFrame, section: str, palette, build_progress: float = 0.0,
               blackout: bool = False) -> tuple[dict, dict]:
        dt = 0.0 if self.last_t is None else max(0.0, f.t - self.last_t)
        self.last_t = f.t
        for name, inst in f.instruments.items():
            tau = STROBE_TAU_S if self._intent_of(name) == "strobe" else (
                FLASH_TAU_S if self._intent_of(name) == "dimmer_flash" else ONSET_TAU_S)
            e = self.env.get(name, 0.0) * math.exp(-dt / tau)
            self.env[name] = 1.0 if inst.onset else e

        gain = self.cfg.section_gain.get(section, 1.0)
        if section == "build":
            gain += (1.0 - gain) * build_progress
        lights = {
            g: {"dimmer": 0.0, "rgb": list(palette[i % 3]), "white": 0.0, "strobe": 0.0, "chase": 0.0,
                "chase_step": self.chase_step[g]}
            for i, g in enumerate(self.groups)
        }
        base = {g: 0.0 for g in self.groups}
        visuals: dict[str, float] = {}
        for name, m in self.cfg.mapping.items():
            inst = f.instruments.get(name)
            if inst is None:
                continue
            ok = self._allowed(m, section)
            level, env = inst.level, self.env.get(name, 0.0)
            for g, intent in (m.get("lights") or {}).items():
                L = lights[g]
                if intent == "dimmer_base":
                    base[g] = max(base[g], 0.3 + 0.7 * level)
                elif intent == "dimmer_flash":
                    L["dimmer"] = max(L["dimmer"], env if ok else 0.0)
                elif intent == "hue_shift":
                    i = self.groups.index(g)
                    L["rgb"] = list(_lerp(palette[i % 3], palette[(i + 1) % 3], level if ok else 0.0))
                elif intent == "white":
                    L["white"] = max(L["white"], level if ok else 0.0)
                elif intent == "strobe":
                    if ok and section in self.cfg.strobe_sections:
                        L["strobe"] = max(L["strobe"], env)
                elif intent == "chase":
                    if ok and inst.onset:
                        self.chase_step[g] += 1
                    L["chase"] = max(L["chase"], env if ok else 0.0)
                    L["chase_step"] = self.chase_step[g]
            if m.get("td"):
                visuals[m["td"]] = round(max(level, env) if ok else 0.0, 4)

        for g, L in lights.items():
            L["dimmer"] = 0.0 if blackout else min(1.0, max(L["dimmer"], base[g]) * gain)
            if blackout:
                L["white"] = L["strobe"] = L["chase"] = 0.0
            for k in ("dimmer", "white", "strobe", "chase"):
                L[k] = round(L[k], 4)
            L["rgb"] = [round(c, 4) for c in L["rgb"]]
        visuals["intensity"] = 0.0 if blackout else round(gain, 4)
        return lights, visuals

    def _intent_of(self, name: str) -> str | None:
        lights = (self.cfg.mapping.get(name) or {}).get("lights") or {}
        return next(iter(lights.values()), None)
