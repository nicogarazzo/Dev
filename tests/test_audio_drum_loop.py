"""F1 con el audio de `drum_loop` / `song` (tests originales de PR #5, portados a la
API unificada). Es una segunda fuente de audio sintetico, independiente de `make_track`."""
import json

import numpy as np
import pytest

from avi.audio import AnalyzerConfig, analyze_array
from avi.audio.spectrum import StreamingSTFT
from avi.audio.synth import drum_loop, kick, place, song, voice_tone
from avi.cli import summarize

SR = 48000
BPM = 126.0
BEAT = 60.0 / BPM


@pytest.fixture(scope="module")
def cfg():
    return AnalyzerConfig.load()


@pytest.fixture(scope="module")
def loop_frames(cfg):
    return analyze_array(drum_loop(12.0, BPM, SR, bass_hz=110.0), SR, cfg)


def onsets(frames, name):
    return [f.t for f in frames if f.instruments[name].onset]


def levels(frames, name, skip=200):
    return np.array([f.instruments[name].level for f in frames[skip:]])


def test_spectrogram_peak_at_tone_frequency():
    stft = StreamingSTFT(2048, 512)
    t = np.arange(SR) / SR
    frames = list(stft.push(np.sin(2 * np.pi * 1000.0 * t).astype(np.float32)))
    assert len(frames) == SR // 512
    freqs = stft.freqs(SR)
    assert abs(freqs[int(np.argmax(frames[-1]))] - 1000.0) < freqs[1]


def test_kick_onsets_land_on_beats(loop_frames):
    kicks = onsets(loop_frames, "kick")
    expected = int(12.0 / BEAT) + 1
    assert abs(len(kicks) - expected) <= 2
    errors = [abs(t - round(t / BEAT) * BEAT) for t in kicks]
    assert max(errors) < 0.045          # dentro de ~4 frames del golpe real


def test_snare_and_hats_onsets(loop_frames):
    n_beats = int(12.0 / BEAT) + 1
    assert abs(len(onsets(loop_frames, "snare")) - n_beats // 2) <= 3
    hats = len(onsets(loop_frames, "hats"))
    assert 0.8 * 2 * (n_beats - 1) <= hats <= 1.2 * 2 * n_beats


def test_bpm_detected(loop_frames):
    assert abs(loop_frames[-1].bpm - BPM) < 3.0
    # y no se cae al medio tiempo con el tiempo
    late = [f.bpm for f in loop_frames if f.t > 6.0]
    assert all(abs(b - BPM) < 3.0 for b in late)


def test_kick_and_bass_drone_are_separated(cfg):
    """Bombo cada beat + bajo sostenido a 110 Hz (se pisan en frecuencia)."""
    canvas = np.zeros(int(12 * SR), dtype=np.float32)
    n_beats = int(12.0 / BEAT) + 1
    for i in range(n_beats):
        place(canvas, kick(SR), i * BEAT, SR, 1.0)
    canvas += voice_tone(SR, 110.0, 12.0)[: len(canvas)] * 0.8
    canvas /= np.abs(canvas).max()
    frames = analyze_array(canvas, SR, cfg)
    assert abs(len(onsets(frames, "kick")) - n_beats) <= 1
    assert len(onsets(frames, "bass")) == 0
    kick_lvl, bass_lvl = levels(frames, "kick"), levels(frames, "bass")
    assert bass_lvl.min() > 0.2          # el bajo nunca "desaparece" cuando pega el bombo
    assert bass_lvl.std() < kick_lvl.std()  # el bajo es estable, el bombo pulsa


def test_steady_tone_produces_no_kick_onsets(cfg):
    frames = analyze_array(voice_tone(SR, 90.0, 10.0), SR, cfg)
    assert len(onsets(frames, "kick")) <= 2  # a lo sumo el arranque


def test_bass_tracker_adapts_to_low_bass(cfg):
    """Bajo a 90 Hz, fuera del nominal 150-400: el rastreador debe bajar su rango."""
    frames = analyze_array(voice_tone(SR, 90.0, 12.0), SR, cfg)
    start = frames[10].instruments["bass"].hz
    end = frames[-1].instruments["bass"].hz
    assert start[0] >= 150.0
    assert end[0] <= 100.0
    assert end[0] >= 60.0  # nunca sale del rango de busqueda


def test_song_sections_change_levels(cfg):
    frames = analyze_array(song(30.0, BPM, SR), SR, cfg)

    def mean_level(name, a, b):
        return float(np.mean([f.instruments[name].level for f in frames if a <= f.t < b]))

    assert mean_level("kick", 2, 9) < 0.15 < mean_level("kick", 22, 29)
    assert mean_level("sub", 2, 9) < mean_level("sub", 22, 29)
    assert mean_level("hats", 2, 9) < mean_level("hats", 12, 19)
    assert abs(frames[-1].bpm - BPM) < 3.0


def test_summary_and_json_roundtrip(loop_frames):
    summary = summarize(loop_frames)
    assert set(summary) >= {"bpm", "beats", "instruments"}
    assert set(summary["instruments"]["kick"]) >= {"onsets", "final_hz", "mean_level"}
    payload = json.dumps([f.to_dict() for f in loop_frames[:5]])
    assert '"kick"' in payload
