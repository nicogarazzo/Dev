import json
import threading
import urllib.request

import numpy as np
import pytest

from avi.audio import AnalyzerConfig
from avi.audio.synth import drum_loop
from avi.cli import build_parser
from avi.ui import server as ui_server
from avi.ui.demo import demo_song, resample
from avi.ui.spectrum import SpectrumTap
from avi.ui.timeline import build_timeline, merge_payloads


SR = 48000


def test_spectrum_tap_bands_and_peak():
    tap = SpectrumTap(SR, n_bands=48)
    t = np.arange(SR // 2) / SR
    specs = tap.push(np.sin(2 * np.pi * 1000 * t))
    assert len(specs) == len(t) // 512
    last = specs[-1]
    assert last.shape == (48,)
    assert 0.0 <= last.min() and last.max() <= 1.0
    # La banda mas fuerte es la que contiene 1 kHz.
    assert abs(tap.centers[int(np.argmax(last))] - 1000) / 1000 < 0.15


def test_demo_song_sections_are_whole_bars():
    audio, marks = demo_song(126, SR)
    bar = 4 * 60 / 126
    assert [m["name"] for m in marks] == ["calm", "build", "drop", "break", "drop"]
    for m in marks:
        assert abs(((m["end"] - m["start"]) / bar) - round((m["end"] - m["start"]) / bar)) < 1e-3
    assert abs(len(audio) / SR - marks[-1]["end"]) < 0.01
    assert np.abs(audio).max() <= 1.0


def test_resample_keeps_length_ratio():
    x = np.random.default_rng(0).standard_normal(48000).astype(np.float32)
    assert len(resample(x, 48000, 24000)) == 24000


def test_timeline_frames_at_fps():
    audio = drum_loop(4.0, 126, SR)
    tl = build_timeline(audio, SR, fps=30)
    assert tl["fps"] == 30 and abs(tl["duration"] - 4.0) < 0.01
    assert 100 <= len(tl["frames"]) <= 121
    f = tl["frames"][-1]
    assert len(f["spectrum"]) == len(tl["meta"]["spectrum_hz"])
    assert set(f["instruments"]) == {t["name"] for t in tl["meta"]["trackers"]}
    assert any(fr["instruments"]["kick"]["onset"] for fr in tl["frames"])
    assert tl["meta"]["fixtures"] and tl["meta"]["palettes"]


def test_merge_keeps_onsets_and_max_level():
    a = {"is_beat": True, "instruments": {"kick": {"level": 0.9, "onset": True}}, "spectrum": [1, 5]}
    b = {"is_beat": False, "instruments": {"kick": {"level": 0.2, "onset": False}}, "spectrum": [4, 2]}
    m = merge_payloads([a, b])
    assert m["is_beat"] and m["instruments"]["kick"] == {"level": 0.9, "onset": True}
    assert m["spectrum"] == [4, 5]


def test_export_html_embeds_timeline_and_audio(tmp_path, monkeypatch):
    # Una cancion corta para que el test sea rapido.
    monkeypatch.setattr(ui_server, "demo_song",
                        lambda bpm, sr: (drum_loop(2.0, bpm, sr), [{"name": "drop", "start": 0, "end": 2.0}]))
    out = ui_server.export_html(tmp_path / "grid.html")
    html = out.read_text()
    assert "<html" not in html.lower()[:200]
    start = html.index('id="avi-embed">') + len('id="avi-embed">')
    data = json.loads(html[start:html.index("</script>", start)])
    assert data["meta"]["mode"] == "demo" and data["sections"][0]["name"] == "drop"
    assert data["audio_b64"].startswith("UklGR")  # "RIFF"


def test_server_serves_page_timeline_and_audio(monkeypatch):
    monkeypatch.setattr(ui_server, "demo_song",
                        lambda bpm, sr: (drum_loop(1.0, bpm, sr), [{"name": "calm", "start": 0, "end": 1.0}]))
    httpd = ui_server.serve(port=0, open_browser=False)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        page = urllib.request.urlopen(base + "/").read().decode()
        assert page.startswith("<!doctype html>") and "AVI" in page
        assert json.load(urllib.request.urlopen(base + "/api/mode")) == {"mode": "demo"}
        tl = json.load(urllib.request.urlopen(base + "/timeline.json"))
        assert tl["frames"] and tl["sections"][0]["name"] == "calm"
        assert urllib.request.urlopen(base + "/audio.wav").read(4) == b"RIFF"
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(base + "/events")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_live_source_take_merges_pending():
    live = ui_server.LiveSource(AnalyzerConfig.load())
    live.feed(drum_loop(1.0, 126, SR))
    frame = live.take()
    assert frame is not None and "spectrum" in frame
    assert live.take() is None


def test_cli_ui_parser():
    a = build_parser().parse_args(["ui", "--live", "--device", "VB-Cable", "--port", "9090", "--no-browser"])
    assert a.live and a.device == "VB-Cable" and a.port == 9090 and a.no_browser
    assert build_parser().parse_args(["ui", "--export", "x.html"]).export == "x.html"
