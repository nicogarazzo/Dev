"""Reloj de compas y detector de secciones (calm / build / drop / break).

El detector trabaja por compas: junta estadisticas de los frames de cada compas y, en
cada downbeat, decide la seccion con reglas simples y predecibles (PLAN_MVP.md §6).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from avi.audio import AudioFrame

from .config import SectionRules


class BarClock:
    """Beats y compases a partir de los AudioFrame.

    Usa los beats del analizador cuando hay tempo; si no llegan (intro sin bombo,
    silencio), sigue contando solo con el ultimo periodo conocido para que el cerebro
    nunca se quede sin compas. Devuelve True en el frame que empieza un compas.
    """

    def __init__(self, default_bpm: float = 120.0, beats_per_phrase: int = 16):
        self.period = 60.0 / default_bpm
        self.beats_per_phrase = beats_per_phrase
        self.last_beat_t: float | None = None
        self.beat_in_bar = 0          # 1..4 (0 antes del primer beat)
        self.bars = 0                 # compases completos empezados
        self.phrase_start = False     # el compas que acaba de empezar abre frase
        self.synthetic = False        # el ultimo beat lo puso el reloj, no el analisis

    def push(self, f: AudioFrame) -> tuple[bool, bool]:
        """-> (hubo beat, empieza compas)."""
        beat = False
        if f.is_beat and f.beat > 0:
            if f.bpm:
                self.period = 60.0 / f.bpm
            beat, self.synthetic = True, False
            nxt = f.beat
        elif self.last_beat_t is None:
            if f.t >= self.period:     # sin beats desde el arranque: reloj propio
                beat, self.synthetic = True, True
                nxt = 1
        elif f.t - self.last_beat_t >= self.period * (1.5 if not self.synthetic else 1.0):
            beat, self.synthetic = True, True
            nxt = self.beat_in_bar % 4 + 1
        if not beat:
            return False, False
        self.last_beat_t = f.t
        # dos downbeats seguidos (el analizador movio el compas) cuentan como compas nuevo
        downbeat = nxt == 1
        self.beat_in_bar = nxt
        if downbeat:
            self.bars += 1
            if f.bpm and not self.synthetic:
                self.phrase_start = int(round(f.phrase_pos * self.beats_per_phrase)) % self.beats_per_phrase == 0
            else:
                self.phrase_start = (self.bars - 1) % max(1, self.beats_per_phrase // 4) == 0
        return True, downbeat


@dataclass
class BarStats:
    energy: float = 0.0
    loudness_db: float = -120.0
    kick_hits: int = 0
    kick_level: float = 0.0
    perc_hits: int = 0            # golpes de hats + snare
    frames: int = 0
    duration_s: float = 0.0


class _Acc:
    def __init__(self):
        self.e = self.db = self.kl = 0.0
        self.kick = self.perc = self.n = 0
        self.t0 = self.t1 = 0.0

    def add(self, f: AudioFrame) -> None:
        inst = f.instruments
        if not self.n:
            self.t0 = f.t
        self.t1 = f.t
        self.n += 1
        self.e += f.energy
        self.db += 10 ** (f.loudness_db / 10)
        if "kick" in inst:
            self.kick += inst["kick"].onset
            self.kl += inst["kick"].level
        self.perc += sum(inst[n].onset for n in ("hats", "snare") if n in inst)

    def close(self) -> BarStats:
        n = max(1, self.n)
        return BarStats(
            energy=self.e / n, loudness_db=float(10 * np.log10(self.db / n + 1e-12)),
            kick_hits=self.kick, kick_level=self.kl / n, perc_hits=self.perc, frames=self.n,
            duration_s=self.t1 - self.t0,
        )


def _slope(values) -> float:
    y = np.asarray(values, dtype=float)
    if len(y) < 2:
        return 0.0
    x = np.arange(len(y)) - (len(y) - 1) / 2
    return float(x @ (y - y.mean()) / (x @ x))


class SectionDetector:
    """Una seccion por compas, con histeresis.

    candidata del compas -> debe repetirse `hysteresis_bars` compases para contar,
    salvo el drop con salto de volumen, que entra en el compas siguiente.
    """

    def __init__(self, rules: SectionRules | None = None, hysteresis_bars: int = 2):
        self.r = rules or SectionRules()
        self.hysteresis = max(1, hysteresis_bars)
        self.section = "calm"
        self.bars_in_section = 0
        self.candidate = "calm"
        self.candidate_bars = 0
        self.history: deque[BarStats] = deque(maxlen=16)
        self.had_kick = False          # hubo bombo antes: sin el ahora es break, no calm
        self.build_progress = 0.0      # 0..1 dentro del build (para subir intensidad)
        self._acc = _Acc()
        self.last: BarStats | None = None
        self.last_reason = ""

    def push(self, f: AudioFrame) -> None:
        self._acc.add(f)

    def close_bar(self, bar_s: float = 0.0) -> str:
        """Cierra el compas en curso y devuelve la seccion vigente. Un compas de menos
        de la mitad de `bar_s` (arranque, el analizador movio el downbeat) no cuenta."""
        bar = self._acc.close()
        self._acc = _Acc()
        if bar.frames == 0 or bar.duration_s < 0.5 * bar_s:
            return self.section
        cand, fast, why = self._classify(bar)
        self.history.append(bar)
        self.last = bar
        if cand == self.candidate:
            self.candidate_bars += 1
        else:
            self.candidate, self.candidate_bars = cand, 1
        self.bars_in_section += 1
        if cand != self.section and (fast or self.candidate_bars >= self.hysteresis):
            self.section, self.bars_in_section, self.last_reason = cand, 1, why
            self.build_progress = 0.0
        if self.section == "build":
            self.build_progress = min(1.0, self.bars_in_section / 8)
        if bar.kick_hits >= self.r.kick_hits_present:
            self.had_kick = True
        return self.section

    def _classify(self, bar: BarStats) -> tuple[str, bool, str]:
        r = self.r
        prev = list(self.history)[-r.build_bars:]
        kick = bar.kick_hits >= r.kick_hits_present
        dense = bar.kick_hits >= r.kick_hits_dense
        peak_db = max([b.loudness_db for b in self.history] + [bar.loudness_db])
        loud = bar.loudness_db >= peak_db - r.drop_db_from_peak
        rise = bar.loudness_db - float(np.mean([b.loudness_db for b in prev])) if len(prev) >= 2 else 0.0
        # tras un build o un break basta el salto normal; desde calm (build no detectado)
        # hace falta el doble, para no confundir "entra el beat" con un drop
        jump = rise >= r.drop_jump_db * (1 if self.section in ("build", "break") else 2)

        if dense and loud:
            if self.section == "drop":
                return "drop", False, "sigue el drop"
            if jump:
                return "drop", True, "salto de volumen + bombo denso"
            if len(self.history) < r.build_bars:   # AVI arranco con la cancion ya arriba
                return "drop", False, "bombo denso + volumen alto desde el inicio"
        if self.section == "drop" and kick and bar.loudness_db >= peak_db - r.drop_hold_db:
            return "drop", False, "sigue el drop"
        if not kick and self.had_kick:
            return "break", False, "se fue el bombo"
        if len(prev) >= r.build_bars and bar.perc_hits >= r.build_min_hits:
            window = prev + [bar]
            hits = [b.perc_hits for b in window]
            dens = _slope(hits)
            db = _slope([b.loudness_db for b in window])
            if (dens >= r.build_density_slope and dens >= r.build_density_rel * np.mean(hits)) or db >= r.build_db_slope:
                return "build", False, f"sube: {dens:+.1f} golpes/compas, {db:+.1f} dB/compas"
            if (self.section == "build" and self.bars_in_section < r.build_max_flat_bars
                    and bar.perc_hits >= 0.8 * np.mean(hits[:-1])):
                return "build", False, "sigue el build"
        return "calm", False, "sin bombo denso ni subida"
