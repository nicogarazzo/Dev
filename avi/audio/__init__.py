"""F1 - Analisis adaptativo de audio: espectrograma, separacion percusivo/armonico,
rastreadores por instrumento (huella espectral + mascara suave), golpes y BPM.

Ver docs/PLAN_MVP.md (seccion 4) y docs/F1_ANALISIS.md.
"""
from .analyzer import Analyzer, AudioFrame, InstrumentState, analyze_array
from .config import AnalyzerConfig, TrackerSpec
from .io import read_audio, write_wav

__all__ = [
    "Analyzer", "AudioFrame", "InstrumentState", "analyze_array",
    "AnalyzerConfig", "TrackerSpec", "read_audio", "write_wav",
]
