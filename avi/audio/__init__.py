"""F1 - Analisis adaptativo de audio: captura, espectrograma, rastreadores por
instrumento (huella espectral + mascara suave), onsets y BPM.

Uso:
    from avi.audio import Analyzer
    analyzer = Analyzer()                 # lee config/bands.yaml
    for frame in analyzer.process(block): # block: np.ndarray mono float32
        frame.instruments["kick"].level, frame.bpm, ...

Ver docs/PLAN_MVP.md, seccion 4.
"""
from .analyzer import Analyzer, AnalysisFrame, analyze_signal, load_config, summarize
from .spectrogram import Spectrogram
from .tempo import TempoTracker
from .trackers import AdaptationConfig, InstrumentTracker, TrackerBank, TrackerConfig, TrackerState

__all__ = [
    "Analyzer", "AnalysisFrame", "analyze_signal", "load_config", "summarize",
    "Spectrogram", "TempoTracker",
    "AdaptationConfig", "InstrumentTracker", "TrackerBank", "TrackerConfig", "TrackerState",
]
