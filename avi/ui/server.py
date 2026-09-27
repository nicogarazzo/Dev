"""Servidor local de la UI (solo libreria estandar).

    avi ui                      # demo: cancion de prueba de 1 minuto, se escucha en el navegador
    avi ui --file cancion.wav   # igual, con tu archivo
    avi ui --live               # en vivo desde el loopback (config/local.yaml -> audio_input)
    avi ui --export out/avi_demo.html   # un HTML autocontenido (timeline + audio) para compartir

Rutas: /  (la pantalla), /api/mode, /timeline.json y /audio.wav (demo/archivo),
/api/meta y /events (en vivo, Server-Sent Events a ~30 cuadros/s).
"""
from __future__ import annotations

import base64
import io
import json
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from avi.audio import Analyzer, AnalyzerConfig, read_audio

from .demo import demo_song, resample
from .spectrum import SpectrumTap
from .timeline import build_timeline, frame_payload, merge_payloads, meta

STATIC = Path(__file__).resolve().parent / "static"
PAGE_HEAD = (
    '<!doctype html><html lang="es"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
    "</head><body>\n"
)
PAGE_TAIL = "\n</body></html>\n"


def page_fragment() -> str:
    """La pantalla sin <html>/<head>/<body> (asi tambien se publica como Artifact)."""
    return (STATIC / "index.html").read_text(encoding="utf-8")


def wav_bytes(audio: np.ndarray, sr: int) -> bytes:
    x = np.asarray(audio, dtype=np.float64)
    peak = np.abs(x).max() if len(x) else 0.0
    if peak > 1.0:
        x = x / peak
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def prepare_source(file: str | Path | None, cfg: AnalyzerConfig, bpm: float = 126.0) -> tuple[dict, bytes]:
    """Timeline + WAV para los modos demo y archivo."""
    if file:
        audio, sr = read_audio(file)
        tl = build_timeline(audio, sr, cfg, mode="file", title=Path(file).name)
    else:
        audio, marks = demo_song(bpm, cfg.sample_rate)
        sr = cfg.sample_rate
        tl = build_timeline(audio, sr, cfg, mode="demo", title=f"cancion de prueba · {bpm:g} BPM")
        tl["sections"] = marks
    return tl, wav_bytes(audio, sr)


def export_html(out: str | Path, cfg: AnalyzerConfig | None = None, file: str | Path | None = None,
                audio_rate: int = 24000) -> Path:
    """HTML autocontenido: la pantalla + timeline + audio (remuestreado para que pese menos)."""
    cfg = cfg or AnalyzerConfig.load()
    if file:
        audio, sr = read_audio(file)
        tl = build_timeline(audio, sr, cfg, mode="file", title=Path(file).name)
    else:
        audio, marks = demo_song(126.0, cfg.sample_rate)
        sr = cfg.sample_rate
        tl = build_timeline(audio, sr, cfg, mode="demo", title="cancion de prueba · 126 BPM")
        tl["sections"] = marks
    small = resample(np.asarray(audio, dtype=np.float32), sr, audio_rate)
    tl["audio_b64"] = base64.b64encode(wav_bytes(small, audio_rate)).decode("ascii")
    embed = json.dumps(tl, separators=(",", ":")).replace("</", "<\\/")
    html = page_fragment().replace(
        "<!--AVI_EMBED-->", f'<script type="application/json" id="avi-embed">{embed}</script>'
    )
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


class LiveSource:
    """Analiza la entrada de audio en un hilo y guarda el ultimo cuadro para la UI."""

    def __init__(self, cfg: AnalyzerConfig, device=None, channels: int = 2):
        self.cfg = cfg
        self.device = device
        self.channels = channels
        self.analyzer = Analyzer(cfg, cfg.sample_rate)
        self.tap = SpectrumTap(cfg.sample_rate, cfg.fft_size, cfg.hop_size)
        self._pending: list[dict] = []
        self._lock = threading.Lock()
        self._stream = None

    def feed(self, mono: np.ndarray) -> None:
        frames = self.analyzer.process(mono)
        specs = self.tap.push(mono)
        with self._lock:
            for fr, sp in zip(frames, specs):
                self._pending.append(frame_payload(fr, sp))

    def take(self) -> dict | None:
        """Todo lo llegado desde la ultima vez, unido en un cuadro (no se pierden golpes)."""
        with self._lock:
            group, self._pending = self._pending, []
        return merge_payloads(group) if group else None

    def start(self) -> None:
        import sounddevice as sd

        dev = self.device
        if dev is not None and not str(dev).isdigit():
            names = [d["name"] for d in sd.query_devices()]
            match = next((i for i, n in enumerate(names) if str(dev).lower() in n.lower()), None)
            if match is None:
                raise SystemExit(f"dispositivo '{dev}' no encontrado; prueba `avi live --list`")
            dev = match
        elif dev is not None:
            dev = int(dev)

        def cb(indata, frames, t, status):
            self.feed(indata.mean(axis=1))

        self._stream = sd.InputStream(device=dev, channels=self.channels, samplerate=self.cfg.sample_rate,
                                      blocksize=self.cfg.hop_size, callback=cb)
        self._stream.start()


def make_handler(state: dict):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # silencio: la UI hace muchas peticiones
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj) -> None:
            self._send(200, json.dumps(obj, separators=(",", ":")).encode(), "application/json")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                html = PAGE_HEAD + page_fragment() + PAGE_TAIL
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/api/mode":
                return self._json({"mode": state["mode"]})
            if path == "/timeline.json" and state.get("timeline"):
                return self._json(state["timeline"])
            if path == "/audio.wav" and state.get("wav"):
                return self._send(200, state["wav"], "audio/wav")
            if path == "/api/meta" and state.get("meta"):
                return self._json(state["meta"])
            if path == "/events" and state.get("live"):
                return self._events(state["live"])
            self._send(404, b"no encontrado", "text/plain; charset=utf-8")

        def _events(self, live: LiveSource) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    frame = live.take()
                    if frame is not None:
                        self.wfile.write(b"data: " + json.dumps(frame, separators=(",", ":")).encode() + b"\n\n")
                        self.wfile.flush()
                    time.sleep(1 / 30)
            except (BrokenPipeError, ConnectionResetError):
                return

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8080, mode: str = "demo", file=None, device=None,
          cfg: AnalyzerConfig | None = None, open_browser: bool = True) -> ThreadingHTTPServer:
    cfg = cfg or AnalyzerConfig.load()
    state: dict = {"mode": mode}
    if mode == "live":
        live = LiveSource(cfg, device)
        state["live"] = live
        state["meta"] = meta(cfg, live.tap, "live", title=str(device or "entrada por defecto"))
        live.start()
    else:
        print("analizando la cancion..." if file else "generando y analizando la cancion de prueba...")
        state["timeline"], state["wav"] = prepare_source(file, cfg)
    httpd = ThreadingHTTPServer((host, port), make_handler(state))
    url = f"http://{host}:{httpd.server_address[1]}/"
    print(f"AVI · GRID en {url}  (Ctrl+C para salir)")
    if open_browser:
        import webbrowser

        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    return httpd
