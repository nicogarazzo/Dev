import json

from avi.cli import main


def test_synth_then_analyze(tmp_path):
    wav = tmp_path / "toy.wav"
    out = tmp_path / "timeline.json"
    assert main(["synth", str(wav), "--seconds", "8", "--bpm", "120"]) == 0
    assert wav.exists()
    assert main(["analyze", str(wav), "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["sample_rate"] == 48000
    assert len(data["frames"]) > 500
    frame = data["frames"][-1]
    assert set(frame["instruments"]) == {"sub", "kick", "bass", "voice", "snare", "hats"}
    assert {"level", "onset", "hz", "confidence"} <= set(frame["instruments"]["kick"])
