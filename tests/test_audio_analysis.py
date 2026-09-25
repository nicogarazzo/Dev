"""F1: analisis adaptativo con audio sintetico de verdad conocida."""
import json

import numpy as np
import pytest

from avi.audio import AnalyzerConfig, Analyzer, analyze_array, read_audio, write_wav
from avi.audio.spectrum import StreamingSTFT
from avi.audio.synth import make_track
from avi.cli import main

SR = 48000
CFG = AnalyzerConfig.load()


def _match(detected, truth, tol=0.06, after=1.0):
    """(recall, precision) de golpes detectados vs verdad, con tolerancia en s."""
    truth = [g for g in truth if g > after]
    det = [d for d in detected if d > after]
    tp = sum(any(abs(d - g) < tol for d in det) for g in truth)
    fp = sum(not any(abs(d - g) < tol for g in truth) for d in det)
    return tp / max(1, len(truth)), (len(det) - fp) / max(1, len(det))


def _series(frames, name, attr="level"):
    return np.array([getattr(f.instruments[name], attr) for f in frames])


@pytest.fixture(scope="module")
def full_mix():
    tr = make_track(bpm=128, seconds=16, parts=("kick", "bass", "snare", "hats", "pad"))
    return tr, analyze_array(tr.audio, tr.sample_rate, CFG)


def test_config_has_six_trackers_inside_search_ranges():
    assert CFG.names == ["sub", "kick", "bass", "voice", "snare", "hats"]
    for t in CFG.trackers:
        assert t.search_hz[0] <= t.nominal_hz[0] < t.nominal_hz[1] <= t.search_hz[1]
    assert CFG.tracker("kick").transient and not CFG.tracker("bass").transient


def test_stft_sine_peaks_at_its_frequency_with_unit_magnitude():
    stft = StreamingSTFT(2048, 512)
    t = np.arange(SR) / SR
    mags = list(stft.push(np.sin(2 * np.pi * 1000 * t)))
    freqs = stft.freqs(SR)
    last = mags[-1]
    assert abs(freqs[np.argmax(last)] - 1000) < freqs[1]
    assert 0.8 < last.max() <= 1.05


def test_block_size_does_not_change_the_result():
    tr = make_track(seconds=5)
    a = analyze_array(tr.audio, SR, CFG, block_size=256)
    b = analyze_array(tr.audio, SR, CFG, block_size=5000)
    assert len(a) == len(b)
    for name in CFG.names:
        np.testing.assert_allclose(_series(a, name), _series(b, name), atol=1e-9)
        assert [f.instruments[name].onset for f in a] == [f.instruments[name].onset for f in b]


def test_kick_and_bass_overlapping_are_separated(full_mix):
    """El bajo (110 Hz, sostenido) cae dentro del rango del bombo: aun asi el nivel del
    bombo pulsa con cada golpe y el del bajo no."""
    tr, frames = full_mix
    t = np.array([f.t for f in frames])
    on_kick = np.array([any(0 <= x - k < 0.1 for k in tr.onsets["kick"]) for x in t])
    late = t > 4
    kick, bass = _series(frames, "kick"), _series(frames, "bass")
    assert kick[late & on_kick].mean() > 3 * kick[late & ~on_kick].mean()
    assert bass[late & on_kick].mean() < 1.25 * bass[late & ~on_kick].mean()
    assert bass[late].mean() > 0.3  # el bajo sigue presente, no se lo comio el bombo


def test_transient_onsets_match_ground_truth(full_mix):
    tr, frames = full_mix
    for name, min_recall in (("kick", 0.95), ("snare", 0.9), ("hats", 0.9)):
        det = [f.t for f in frames if f.instruments[name].onset]
        recall, precision = _match(det, tr.onsets[name])
        assert recall >= min_recall, (name, recall)
        assert precision >= 0.9, (name, precision)


def test_tonal_trackers_never_report_onsets(full_mix):
    _, frames = full_mix
    for name in ("sub", "bass", "voice"):
        assert not any(f.instruments[name].onset for f in frames)


@pytest.mark.parametrize("bpm", [90, 128, 174])
def test_bpm_and_beats_lock_to_the_kick(bpm):
    tr = make_track(bpm=bpm, seconds=14, parts=("kick", "bass", "hats"))
    frames = analyze_array(tr.audio, SR, CFG)
    assert frames[-1].bpm == pytest.approx(bpm, abs=1.0)
    beats = [f.t for f in frames if f.is_beat and f.t > 8]
    assert len(beats) >= int((14 - 8) * bpm / 60) - 1
    err = [min(abs(b - k) for k in tr.onsets["kick"]) for b in beats]
    assert np.median(err) < 0.03
    assert {f.beat for f in frames if f.is_beat} == {1, 2, 3, 4}


def test_tracker_follows_the_bass_but_stays_in_its_search_range():
    """Un bajo en 440 Hz (sobre el nominal 150-400): el rango del rastreador sube hacia
    ahi, sin salir nunca de search_hz."""
    tr = make_track(seconds=20, parts=("bass",), bass_hz=(440.0,))
    frames = analyze_array(tr.audio, SR, CFG)
    spec = CFG.tracker("bass")
    for f in frames:
        for t in CFG.trackers:
            lo, hi = f.instruments[t.name].hz
            assert t.search_hz[0] <= lo < hi <= t.search_hz[1]
    lo_start = frames[int(1 * 93.75)].instruments["bass"].hz[0]
    lo_end = frames[-1].instruments["bass"].hz[0]
    assert lo_end > lo_start + 100
    assert lo_end > spec.nominal_hz[0]


def test_silence_drops_levels_and_confidence_back_to_nominal():
    tr = make_track(seconds=8)
    audio = np.concatenate([tr.audio, np.zeros(SR * 5)])
    frames = analyze_array(audio, SR, CFG)
    before, last = frames[int(7.5 * 93.75)], frames[-1]
    assert before.instruments["kick"].confidence > CFG.min_confidence
    for t in CFG.trackers:
        s = last.instruments[t.name]
        assert s.level < 0.01
        assert s.confidence < CFG.min_confidence
        assert s.hz == tuple(t.nominal_hz)
    assert last.energy < 0.01


def test_frame_dict_matches_showstate_instrument_schema(full_mix):
    _, frames = full_mix
    d = frames[-1].to_dict()
    assert set(d["instruments"]) == set(CFG.names)
    for inst in d["instruments"].values():
        assert set(inst) == {"level", "onset", "hz", "confidence"}
        assert 0.0 <= inst["level"] <= 1.0 and 0.0 <= inst["confidence"] <= 1.0
    for key in ("t", "bpm", "beat", "bar", "is_beat", "phrase_pos", "energy", "energy_long", "brightness"):
        assert key in d
    json.dumps(d)


def test_streaming_analyzer_is_fast_enough_for_live():
    """Un segundo de audio debe procesarse muy por debajo de un segundo."""
    import time

    tr = make_track(seconds=4)
    an = Analyzer(CFG, SR)
    t0 = time.perf_counter()
    for i in range(0, len(tr.audio), 512):
        an.process(tr.audio[i:i + 512])
    assert (time.perf_counter() - t0) / 4 < 0.5


def test_wav_roundtrip_and_cli_analyze(tmp_path, capsys):
    tr = make_track(seconds=10)
    wav = write_wav(tmp_path / "song.wav", tr.audio, SR)
    audio, sr = read_audio(wav)
    assert sr == SR and len(audio) == len(tr.audio)
    out = tmp_path / "song.json"
    assert main(["analyze", str(wav), "-o", str(out), "--fps", "30"]) == 0
    tl = json.loads(out.read_text())
    assert tl["summary"]["bpm"] == pytest.approx(128, abs=1.0)
    assert abs(len(tl["frames"]) - 10 * 30) <= 3
    assert sum(f["instruments"]["kick"]["onset"] for f in tl["frames"]) >= 18
    assert "kick" in capsys.readouterr().out
