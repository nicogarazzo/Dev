"""Linea de comandos de AVI.

    avi synth out.wav --seconds 30 --bpm 126     # cancion de juguete (calm -> build -> drop)
    avi analyze cancion.wav --out timeline.json  # analiza offline y guarda un frame por espectro
    avi live --device "VB-Cable"                 # analiza el loopback y muestra niveles en vivo
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from avi.audio import Analyzer, analyze_signal, load_config, summarize
from avi.audio.synth import song
from avi.audio.wavio import read_wav, write_wav


def cmd_synth(a: argparse.Namespace) -> int:
    data = song(a.seconds, a.bpm, a.sample_rate)
    write_wav(a.out, data, a.sample_rate)
    print(f"escrito {a.out}: {a.seconds}s a {a.bpm} BPM, {a.sample_rate} Hz")
    return 0


def cmd_analyze(a: argparse.Namespace) -> int:
    samples, sr = read_wav(a.wav)
    cfg = load_config(a.config)
    frames = analyze_signal(samples, sr, cfg, block_size=int(cfg.get("block_size", 512)))
    summary = summarize(frames)
    if a.out:
        payload = {"source": str(a.wav), "sample_rate": sr, "summary": summary,
                   "frames": [f.as_dict() for f in frames]}
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(payload, ensure_ascii=False, indent=None))
        print(f"timeline: {a.out} ({len(frames)} frames)")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _bar(x: float, width: int = 20) -> str:
    n = int(max(0.0, min(1.0, x)) * width)
    return "#" * n + "." * (width - n)


def cmd_live(a: argparse.Namespace) -> int:
    try:
        import sounddevice as sd
    except ImportError:
        print("falta sounddevice: pip install sounddevice", file=sys.stderr)
        return 2
    cfg = load_config(a.config)
    sr = int(cfg.get("sample_rate", 48000))
    block = int(cfg.get("block_size", 512))
    analyzer = Analyzer(cfg, sr)
    names = analyzer.bank.names
    last_print = [0.0]

    def callback(indata, frames, time_info, status):
        for frame in analyzer.process(indata[:, 0]):
            pass
        now = time.monotonic()
        if analyzer.last and now - last_print[0] > a.interval:
            last_print[0] = now
            f = analyzer.last
            cols = [f"{n:>5} {_bar(f.instruments[n].level, 12)}{'*' if f.instruments[n].onset else ' '}" for n in names]
            hz = " ".join(f"{n}:{int(f.instruments[n].hz[0])}-{int(f.instruments[n].hz[1])}" for n in names)
            sys.stdout.write("\r" + f"bpm {f.bpm:6.1f} bar {f.bar:3d} beat {f.beat} | " + " ".join(cols) + " | " + hz + "   ")
            sys.stdout.flush()

    device = a.device
    if device is None:
        try:
            local = Path("config/local.yaml")
            if local.exists():
                import yaml
                device = (yaml.safe_load(local.read_text()) or {}).get("audio_input")
        except Exception:
            device = None
    print(f"escuchando {device or 'entrada por defecto'} a {sr} Hz (Ctrl+C para salir)")
    with sd.InputStream(device=device, channels=1, samplerate=sr, blocksize=block, dtype="float32", callback=callback):
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print()
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="avi", description="AVI: cerebro audio -> luces + visuales")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("synth", help="genera una cancion de juguete en WAV")
    s.add_argument("out")
    s.add_argument("--seconds", type=float, default=30.0)
    s.add_argument("--bpm", type=float, default=126.0)
    s.add_argument("--sample-rate", type=int, default=48000)
    s.set_defaults(func=cmd_synth)

    an = sub.add_parser("analyze", help="analiza un WAV offline")
    an.add_argument("wav")
    an.add_argument("--out", help="timeline JSON (un frame por espectro)")
    an.add_argument("--config", default=None, help="config/bands.yaml alternativo")
    an.set_defaults(func=cmd_analyze)

    lv = sub.add_parser("live", help="analiza la entrada de audio en vivo")
    lv.add_argument("--device", default=None, help="nombre del dispositivo (por defecto config/local.yaml -> audio_input)")
    lv.add_argument("--config", default=None)
    lv.add_argument("--interval", type=float, default=0.1)
    lv.set_defaults(func=cmd_live)

    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
