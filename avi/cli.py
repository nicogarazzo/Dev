"""Linea de comandos de AVI.

    avi synth out/toy.wav --seconds 30 --bpm 126  # cancion de juguete: calm -> build -> drop
    avi analyze cancion.wav -o out/cancion.json   # timeline JSON + resumen (--fps 30 para aligerar)
    avi live                                      # en vivo; dispositivo de config/local.yaml (alias: listen)
    avi demo                                      # pista con verdad conocida -> analisis -> resumen
    avi ui                                        # pantalla TRON en el navegador (demo; --file, --live)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from .audio import AnalyzerConfig, Analyzer, AudioFrame, analyze_array, read_audio


def decimate(frames: list[AudioFrame], fps: float) -> list[dict]:
    """Reduce a `fps` cuadros/s: nivel = maximo del grupo, golpes y beats = cualquiera."""
    if not fps:
        return [f.to_dict() for f in frames]
    groups: dict[int, list[AudioFrame]] = {}
    for f in frames:
        groups.setdefault(int(f.t * fps), []).append(f)
    out = []
    for group in groups.values():
        d = group[-1].to_dict()
        d["is_beat"] = any(f.is_beat for f in group)
        for name, inst in d["instruments"].items():
            inst["level"] = round(max(f.instruments[name].level for f in group), 4)
            inst["onset"] = any(f.instruments[name].onset for f in group)
        out.append(d)
    return out


def summarize(frames: list[AudioFrame]) -> dict:
    if not frames:
        return {"duration_s": 0.0}
    names = list(frames[0].instruments)
    bpms = [f.bpm for f in frames[len(frames) // 2:] if f.bpm]
    last = frames[-1]
    return {
        "duration_s": round(last.t, 2),
        "bpm": round(float(np.median(bpms)), 2) if bpms else None,
        "beats": sum(f.is_beat for f in frames),
        "instruments": {
            n: {
                "onsets": sum(f.instruments[n].onset for f in frames),
                "mean_level": round(float(np.mean([f.instruments[n].level for f in frames])), 3),
                "final_hz": [int(round(x)) for x in last.instruments[n].hz],
                "final_confidence": round(last.instruments[n].confidence, 2),
            }
            for n in names
        },
    }


def print_summary(s: dict, out=None) -> None:
    out = out or sys.stdout
    print(f"duracion {s['duration_s']} s · BPM {s.get('bpm')} · beats {s.get('beats')}", file=out)
    for n, d in s.get("instruments", {}).items():
        print(f"  {n:6s} golpes {d['onsets']:4d}  nivel medio {d['mean_level']:.2f}  "
              f"rango {d['final_hz'][0]}-{d['final_hz'][1]} Hz  confianza {d['final_confidence']:.2f}", file=out)


def cmd_analyze(a) -> int:
    cfg = AnalyzerConfig.load(a.config)
    audio, sr = read_audio(a.file)
    t0 = time.time()
    frames = analyze_array(audio, sr, cfg)
    frame_rate = sr / cfg.hop_size
    summary = summarize(frames)
    timeline = {
        "source": str(a.file),
        "sample_rate": sr,
        "frame_rate": round(frame_rate, 3),
        "fps": a.fps,
        "summary": summary,
        "frames": decimate(frames, a.fps),
    }
    out = Path(a.output) if a.output else Path("out") / (Path(a.file).stem + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(timeline))
    print_summary(summary)
    print(f"timeline -> {out}  ({len(timeline['frames'])} cuadros, {time.time() - t0:.1f} s de calculo)")
    return 0


def _bar(v: float, width: int = 8) -> str:
    n = int(round(max(0.0, min(1.0, v)) * width))
    return "#" * n + "." * (width - n)


def render_line(f: AudioFrame) -> str:
    parts = []
    for name, s in f.instruments.items():
        mark = "*" if s.onset else " "
        parts.append(f"{name}{mark}{_bar(s.level)}")
    bpm = f"{f.bpm:5.1f}" if f.bpm else "  ---"
    beat = "o" if f.is_beat else " "
    return f"BPM {bpm} {f.beat}{beat} | " + " ".join(parts)


def cmd_listen(a) -> int:
    try:
        import sounddevice as sd
    except ImportError:
        print("Falta sounddevice: pip install sounddevice", file=sys.stderr)
        return 1
    if a.list:
        print(sd.query_devices())
        return 0
    dev = a.device or _default_device()
    wanted = dev
    if dev is not None and not str(dev).isdigit():
        names = [d["name"] for d in sd.query_devices()]
        dev = next((i for i, n in enumerate(names) if wanted.lower() in n.lower()), None)
        if dev is None:
            print(f"dispositivo '{wanted}' no encontrado; usa --list", file=sys.stderr)
            return 1
    elif dev is not None:
        dev = int(dev)
    cfg = AnalyzerConfig.load(a.config)
    an = Analyzer(cfg, cfg.sample_rate)
    state = {"last": None}

    def cb(indata, frames, t, status):
        for fr in an.process(indata.mean(axis=1)):
            if a.json:
                sys.stdout.write(json.dumps(fr.to_dict()) + "\n")
            state["last"] = fr

    with sd.InputStream(device=dev, channels=a.channels, samplerate=cfg.sample_rate,
                        blocksize=cfg.hop_size, callback=cb):
        t_end = time.time() + a.seconds if a.seconds else None
        while t_end is None or time.time() < t_end:
            time.sleep(0.05)
            if not a.json and state["last"] is not None:
                sys.stdout.write("\r" + render_line(state["last"])[:160])
                sys.stdout.flush()
    print()
    return 0


def cmd_synth(a) -> int:
    from .audio.io import write_wav
    from .audio.synth import song

    wav = write_wav(a.out, song(a.seconds, a.bpm, a.sample_rate), a.sample_rate)
    print(f"escrito {wav}: {a.seconds} s a {a.bpm} BPM, {a.sample_rate} Hz (calm -> build -> drop)")
    return 0


def _default_device() -> str | None:
    """`audio_input` de config/local.yaml (lo escribe el setup local, L1)."""
    import yaml

    local = Path("config/local.yaml")
    try:
        return (yaml.safe_load(local.read_text()) or {}).get("audio_input") if local.exists() else None
    except (OSError, yaml.YAMLError):
        return None


def cmd_demo(a) -> int:
    from .audio.io import write_wav
    from .audio.synth import make_track

    tr = make_track(bpm=a.bpm, seconds=a.seconds, parts=("kick", "bass", "snare", "hats", "pad"))
    wav = write_wav(Path(a.output_dir) / "demo.wav", tr.audio, tr.sample_rate)
    print(f"pista sintetica: {wav}  ({a.bpm} BPM, bombo + bajo superpuestos, snare, hats, pad)")
    ns = argparse.Namespace(file=wav, output=Path(a.output_dir) / "demo.json", fps=30.0, config=a.config)
    cmd_analyze(ns)
    print(f"esperado: BPM {a.bpm}, golpes de bombo {len(tr.onsets['kick'])}, "
          f"snare {len(tr.onsets['snare'])}, hats {len(tr.onsets['hats'])}")
    return 0


def cmd_ui(a) -> int:
    from .ui.server import export_html, serve

    cfg = AnalyzerConfig.load(a.config)
    if a.export:
        out = export_html(a.export, cfg, file=a.file)
        print(f"escrito {out} ({out.stat().st_size / 1e6:.1f} MB): abrelo en el navegador")
        return 0
    if a.live:
        httpd = serve(a.host, a.port, "live", device=a.device or _default_device(), cfg=cfg,
                      open_browser=not a.no_browser)
    else:
        httpd = serve(a.host, a.port, "file" if a.file else "demo", file=a.file, cfg=cfg,
                      open_browser=not a.no_browser)
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="avi", description="AVI: cerebro de luces y visuales")
    sub = p.add_subparsers(dest="cmd", required=True)

    sy = sub.add_parser("synth", help="escribe una cancion de juguete en WAV (calm -> build -> drop)")
    sy.add_argument("out")
    sy.add_argument("--seconds", type=float, default=30.0)
    sy.add_argument("--bpm", type=float, default=126.0)
    sy.add_argument("--sample-rate", type=int, default=48000)
    sy.set_defaults(func=cmd_synth)

    an = sub.add_parser("analyze", help="analiza un archivo y escribe un timeline JSON")
    an.add_argument("file")
    an.add_argument("-o", "--output", "--out", dest="output")
    an.add_argument("--fps", type=float, default=0.0, help="cuadros/s del timeline (0 = todos, ~94/s)")
    an.add_argument("--config")
    an.set_defaults(func=cmd_analyze)

    li = sub.add_parser("live", aliases=["listen"], help="analiza la entrada de audio en vivo")
    li.add_argument("--device", help="nombre o indice (por defecto config/local.yaml -> audio_input)")
    li.add_argument("--list", action="store_true", help="lista dispositivos de audio")
    li.add_argument("--seconds", type=float, default=0, help="0 = hasta Ctrl+C")
    li.add_argument("--channels", type=int, default=2)
    li.add_argument("--json", action="store_true", help="imprime un JSON por frame")
    li.add_argument("--config")
    li.set_defaults(func=cmd_listen)

    de = sub.add_parser("demo", help="genera una pista sintetica y la analiza")
    de.add_argument("--bpm", type=float, default=128.0)
    de.add_argument("--seconds", type=float, default=20.0)
    de.add_argument("--output-dir", default="out")
    de.add_argument("--config")
    de.set_defaults(func=cmd_demo)

    ui = sub.add_parser("ui", help="pantalla TRON en el navegador (demo, archivo o en vivo)")
    ui.add_argument("--file", help="analiza y reproduce este archivo en vez de la cancion de prueba")
    ui.add_argument("--live", action="store_true", help="en vivo desde la entrada de audio")
    ui.add_argument("--device", help="con --live: nombre o indice (por defecto config/local.yaml)")
    ui.add_argument("--host", default="127.0.0.1")
    ui.add_argument("--port", type=int, default=8080)
    ui.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    ui.add_argument("--export", metavar="HTML", help="escribe un HTML autocontenido y sale")
    ui.add_argument("--config")
    ui.set_defaults(func=cmd_ui)
    return p


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.func(a)
    except KeyboardInterrupt:
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main())
