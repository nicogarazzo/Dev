"""F2 - Cerebro: detecta la seccion (calm/build/drop/break), elige escena y paleta
y produce un ShowState por frame de audio. Luces (F3) y TouchDesigner solo lo traducen.

Ver docs/PLAN_MVP.md (secciones 3 y 6) y docs/F2_CEREBRO.md.
"""
from .brain import Brain, ShowState, run_brain, section_spans
from .config import SECTIONS, Scene, SectionRules, ShowConfig
from .scenes import Override
from .sections import BarClock, BarStats, SectionDetector

__all__ = [
    "Brain", "ShowState", "run_brain", "section_spans",
    "SECTIONS", "Scene", "SectionRules", "ShowConfig", "Override",
    "BarClock", "BarStats", "SectionDetector",
]
