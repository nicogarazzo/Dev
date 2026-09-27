"""F2: cerebro (secciones, escenas, paleta, intenciones y ShowState)."""
import json

import numpy as np
import pytest

from avi.audio import AudioFrame, InstrumentState, analyze_array
from avi.audio.synth import arrangement
from avi.brain import Brain, BarClock, SectionDetector, ShowConfig, run_brain, section_spans
from avi.cli import main

NAMES = ("sub", "kick", "bass", "voice", "snare", "hats")
FPS = 100
BPM = 120.0
FRAMES_PER_BEAT = int(FPS * 60 / BPM)          # 50
CFG = ShowConfig.load()


def fake_bars(spec, start_bar=0):
    """Frames sinteticos, compas a compas. spec = [(bars, kick_hits, perc_hits, loudness_db)].

    Beats a 120 BPM exactos; golpes de bombo en los primeros `kick_hits` beats y golpes
    de hats repartidos en el compas."""
    frames, n, bar = [], start_bar * 4 * FRAMES_PER_BEAT, start_bar
    for bars, kicks, perc, db in spec:
        for _ in range(bars):
            bar += 1
            hat_frames = {int(i * 4 * FRAMES_PER_BEAT / perc) for i in range(perc)} if perc else set()
            for i in range(4 * FRAMES_PER_BEAT):
                beat_idx, in_beat = divmod(i, FRAMES_PER_BEAT)
                is_beat = in_beat == 0
                inst = {k: InstrumentState(0.1, False, (0.0, 1.0), 0.9) for k in NAMES}
                if is_beat and beat_idx < kicks:
                    inst["kick"] = InstrumentState(0.9, True, (50.0, 130.0), 0.9)
                if i in hat_frames:
                    inst["hats"] = InstrumentState(0.7, True, (7000.0, 15000.0), 0.9)
                n += 1
                frames.append(AudioFrame(
                    t=n / FPS, instruments=inst, bpm=BPM, beat=beat_idx + 1, bar=bar, is_beat=is_beat,
                    beat_phase=in_beat / FRAMES_PER_BEAT,
                    phrase_pos=(((bar - 1) % 4) * 4 + beat_idx + in_beat / FRAMES_PER_BEAT) / 16,
                    energy=0.5, energy_long=0.5, loudness_db=db, centroid_hz=1000.0, brightness=0.5,
                ))
    return frames


CALM = (8, 0, 2, -24.0)
BUILD = [(2, 4, 4, -20.0), (2, 4, 8, -19.0), (2, 4, 16, -18.0), (2, 4, 32, -17.0)]
DROP = (16, 4, 8, -9.0)
BREAK = (8, 0, 4, -22.0)


def sections_by_bar(frames, cfg=CFG):
    brain = Brain(cfg)
    out = []
    for f in frames:
        s = brain.update(f)
        if s.bar_start:
            out.append(s.section)
    return out, brain


# --- configuracion -----------------------------------------------------------------

def test_example_show_config_loads():
    assert set(CFG.palettes) == {"frio", "fuego", "neon"}
    assert [s.name for s in CFG.scenes] == ["ambiente", "subida", "drop"]
    assert CFG.phrase_beats == 16 and CFG.min_scene_bars == 8 and CFG.section_hysteresis_bars == 2
    assert CFG.groups == ["all", "front", "wave"]
    assert CFG.scenes_for("drop")[0].name == "drop"


def test_bad_show_config_is_rejected():
    with pytest.raises(ValueError):
        ShowConfig.from_dict({"palettes": {"x": [[1, 0, 0]]}})
    with pytest.raises(ValueError):
        ShowConfig.from_dict({"scenes": [{"name": "a", "palettes": ["no_existe"]}]})
    with pytest.raises(ValueError):
        Brain(ShowConfig.from_dict({"mapping": {"kick": {"lights": {"all": "laser"}}}}))


# --- reloj y secciones ---------------------------------------------------------------

def test_bar_clock_keeps_counting_without_tempo():
    clock = BarClock(default_bpm=120)
    silent = {k: InstrumentState(0.0, False, (0.0, 1.0), 0.0) for k in NAMES}
    downbeats = []
    for n in range(1, 1001):   # 10 s sin beats del analizador
        f = AudioFrame(n / FPS, silent, None, 0, 0, False, 0.0, 0.0, 0.0, 0.0, -120.0, 0.0, 0.0)
        beat, down = clock.push(f)
        if down:
            downbeats.append(f.t)
    assert len(downbeats) == 5                      # 1 compas cada 2 s
    assert np.allclose(np.diff(downbeats), 2.0, atol=0.02)


def test_sections_follow_the_song_form():
    frames = fake_bars([CALM, *BUILD, DROP, BREAK, (8, 4, 8, -9.0)])
    secs, brain = sections_by_bar(frames)
    # compas n (1..) cierra el compas n-1; el primero no tiene compas previo
    runs = [s for i, s in enumerate(secs) if i == 0 or secs[i - 1] != s]
    assert runs == ["calm", "build", "drop", "break", "drop"]
    first_drop = secs.index("drop")
    assert first_drop == 8 + 8 + 1                   # entra justo en el compas siguiente al salto
    assert secs[first_drop - 1] == "build"
    second_drop = len(secs) - 1 - secs[::-1].index("break") + 1
    assert second_drop == 8 + 8 + 16 + 8 + 1


def test_one_bar_without_kick_does_not_break_the_drop():
    frames = fake_bars([CALM, *BUILD, (8, 4, 8, -9.0), (1, 0, 4, -14.0), (8, 4, 8, -9.0)])
    secs, _ = sections_by_bar(frames)
    assert "break" not in secs
    assert secs[-1] == "drop"


def test_steady_groove_is_not_a_build_and_noise_in_hits_is_ignored():
    rng = np.random.default_rng(3)
    spec = [(1, 0, int(h), -24.0) for h in rng.integers(8, 13, size=24)]
    secs, _ = sections_by_bar(fake_bars(spec))
    assert set(secs) == {"calm"}


def test_starting_in_the_middle_of_a_drop():
    secs, _ = sections_by_bar(fake_bars([(8, 4, 8, -9.0)]))
    assert secs[-1] == "drop"


def test_section_detector_alone():
    det = SectionDetector(hysteresis_bars=2)
    for f in fake_bars([(4, 4, 8, -9.0)]):
        det.push(f)
    assert det.close_bar() in ("calm", "drop")


# --- escenas y paleta ----------------------------------------------------------------

def test_scene_changes_are_quantized_and_drop_enters_on_beat_one():
    frames = fake_bars([CALM, *BUILD, DROP, BREAK])
    states = run_brain(frames)
    scene_changes = [s for s in states if "scene" in s.changes]
    assert [s.scene_name for s in scene_changes] == ["subida", "drop", "ambiente"]
    for s in scene_changes:
        assert s.bar_start and s.frame.beat == 1
        if s.section != "drop":
            assert s.phrase_start
    # la escena del drop entra en el mismo compas que la seccion
    drop = next(s for s in states if s.section == "drop")
    assert drop.scene_name == "drop" and "scene" in drop.changes
    # duracion minima: nunca dos cambios de escena en menos de 8 compases salvo el drop
    t = [s.t for s in scene_changes if s.section != "drop"]
    assert all(b - a >= 8 * 2.0 - 0.1 for a, b in zip(t, t[1:]))


def test_palette_is_shared_and_belongs_to_the_scene():
    states = run_brain(fake_bars([CALM, *BUILD, DROP, BREAK]))
    for s in states[::50]:
        scene = CFG.scene(s.scene)
        if not any("palette" in x.changes for x in states if s.t - 2.1 < x.t <= s.t):
            assert s.palette_name in scene.palettes
            assert s.palette == [list(c) for c in CFG.palettes[s.palette_name]]
        # luces y visuales leen la misma paleta: el grupo front usa el color 2 tal cual
        assert s.lights["front"]["rgb"] == [round(c, 4) for c in s.palette[1]]


def test_palette_crossfades_except_on_drop():
    states = run_brain(fake_bars([CALM, *BUILD, DROP]))
    build_change = next(i for i, s in enumerate(states) if "palette" in s.changes and s.section == "build")
    mid = states[build_change + 50]                  # 1 beat despues, a mitad del cruce de 4 beats
    src, dst = CFG.palettes["frio"], CFG.palettes[states[build_change].palette_name]
    assert mid.palette != [list(c) for c in dst] and mid.palette != [list(c) for c in src]
    drop = next(s for s in states if s.section == "drop" and "palette" in s.changes)
    assert drop.palette == [list(c) for c in CFG.palettes[drop.palette_name]]


def test_override_wins_and_release_returns_to_auto():
    brain = Brain()
    frames = fake_bars([CALM, *BUILD, DROP])
    for f in frames[:800]:
        brain.update(f)
    brain.set_override(scene=2, palette="neon")
    s = brain.update(frames[800])
    assert (s.scene, s.palette_name) == (2, "neon")
    assert s.override == {"scene": 2, "palette": "neon", "blackout": False}
    assert "scene" in s.changes and s.palette == [list(c) for c in CFG.palettes["neon"]]
    brain.set_override(blackout=True)
    s = brain.update(frames[801])
    assert all(g["dimmer"] == 0 and g["strobe"] == 0 for g in s.lights.values())
    assert s.visuals["intensity"] == 0
    for f in frames[802:]:
        s = brain.update(f)
    assert s.scene == 2                               # sigue forzada aunque cambie la musica
    brain.release()
    s = brain.update(frames[-1])
    assert s.override is None and s.scene_name == "drop" and s.section == "drop"
    with pytest.raises(KeyError):
        brain.set_override(scene=99)


# --- intenciones ---------------------------------------------------------------------

def test_kick_flashes_front_and_snare_strobes_only_in_drop():
    states = run_brain(fake_bars([CALM, *BUILD, DROP]))
    hit = next(i for i, s in enumerate(states) if s.section == "drop" and s.instruments["kick"].onset)
    assert states[hit].lights["front"]["dimmer"] == 1.0
    assert states[hit + 30].lights["front"]["dimmer"] < 0.5          # 300 ms despues ya cayo
    assert states[hit].visuals["zoom_pulse"] == 1.0
    assert all(s.lights["all"]["strobe"] == 0 for s in states if s.section != "drop")
    steps = [s.lights["wave"]["chase_step"] for s in states]
    assert steps == sorted(steps) and steps[-1] > 0                    # cada golpe de hats avanza el chase


def test_section_gain_dims_calm_and_break():
    states = run_brain(fake_bars([CALM, *BUILD, DROP, BREAK]))
    peak = {sec: max(s.lights["all"]["dimmer"] for s in states if s.section == sec)
            for sec in ("calm", "drop", "break")}
    assert peak["break"] < peak["calm"] < peak["drop"]


# --- ShowState -----------------------------------------------------------------------

def test_show_state_has_the_plan_contract_and_is_json():
    s = run_brain(fake_bars([DROP]))[-1]
    d = json.loads(json.dumps(s.to_dict()))
    for key in ("t", "bpm", "beat", "bar", "phrase_pos", "section", "scene", "palette", "instruments", "override",
                "td_scene", "td_clip", "palette_name", "lights", "visuals"):
        assert key in d
    assert len(d["palette"]) == 3 and all(len(c) == 3 for c in d["palette"])
    assert set(d["instruments"]) == set(NAMES)
    assert set(d["lights"]["all"]) == {"dimmer", "rgb", "white", "strobe", "chase", "chase_step"}


def test_brain_is_deterministic():
    frames = fake_bars([CALM, *BUILD, DROP])
    a = [s.to_dict() for s in run_brain(frames)]
    b = [s.to_dict() for s in run_brain(frames)]
    assert a == b


# --- con audio: analisis (F1) + cerebro ----------------------------------------------

@pytest.fixture(scope="module")
def song_states():
    audio, truth = arrangement(bpm=126)
    return run_brain(analyze_array(audio, 48000)), truth


def test_brain_on_synthetic_song_finds_every_section(song_states):
    states, truth = song_states
    spans = section_spans(states)
    names = [s["name"] for s in spans]
    assert names == ["calm", "build", "drop", "break", "drop"]
    bar_s = 4 * 60 / 126
    by_name = {}
    for sp in spans:
        by_name.setdefault(sp["name"], []).append(sp)
    true_by = {}
    for tr in truth:
        true_by.setdefault(tr["name"], []).append(tr)
    for got, want in zip(by_name["drop"], true_by["drop"]):
        assert want["start"] <= got["start"] <= want["start"] + 1.5 * bar_s      # drop: en el compas siguiente
    assert true_by["break"][0]["start"] <= by_name["break"][0]["start"] <= true_by["break"][0]["start"] + 3 * bar_s
    assert by_name["build"][0]["start"] < true_by["drop"][0]["start"]


def test_brain_on_synthetic_song_changes_scene_and_palette(song_states):
    states, _ = song_states
    changes = [(s.scene_name, s.palette_name) for s in states if "scene" in s.changes]
    assert [c[0] for c in changes] == ["subida", "drop", "ambiente", "drop"]
    drops = [p for name, p in changes if name == "drop"]
    assert drops[0] != drops[1]                      # el segundo drop rota la paleta


def test_cli_show(tmp_path):
    wav, out = tmp_path / "show.wav", tmp_path / "show.json"
    assert main(["synth", str(wav), "--sections", "--bpm", "126"]) == 0
    assert main(["show", str(wav), "--out", str(out), "--fps", "20"]) == 0
    data = json.loads(out.read_text())
    assert [s["name"] for s in data["sections"]] == ["calm", "build", "drop", "break", "drop"]
    assert any("scene" in c["changes"] for c in data["changes"])
    f = data["frames"][len(data["frames"]) // 2]
    assert {"section", "scene", "palette", "lights", "visuals"} <= set(f)
