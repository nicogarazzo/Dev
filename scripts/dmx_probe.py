"""Sondeo DMX directo (fase L2), sin el software EMU.

    python scripts/dmx_probe.py --list                       # puertos serie candidatos
    python scripts/dmx_probe.py --channel 1 --value 255      # deja el canal 1 al máximo
    python scripts/dmx_probe.py --sweep 1 8 --hold 3         # canales 1..8 uno por uno
    python scripts/dmx_probe.py --blackout

Backend y puerto salen del bloque `dmx:` de config/local.yaml, o de --backend/--port.
"""
import argparse
import glob
import time
from pathlib import Path

import yaml

from avi.outputs.dmx import ArtNetBackend, DmxUniverse, EnttecProBackend, NullBackend

ROOT = Path(__file__).resolve().parents[1]


def load_dmx_cfg():
    local = ROOT / "config" / "local.yaml"
    if local.exists():
        return (yaml.safe_load(local.read_text()) or {}).get("dmx") or {}
    return {}


def make_backend(a, cfg):
    kind = a.backend or cfg.get("backend", "null")
    if kind == "enttec_pro":
        port = a.port or cfg.get("serial_port")
        if not port:
            raise SystemExit("Falta --port o dmx.serial_port en config/local.yaml")
        return EnttecProBackend(port)
    if kind == "artnet":
        return ArtNetBackend(a.host or cfg.get("host", "255.255.255.255"), int(cfg.get("universe", 0)))
    return NullBackend()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true")
    p.add_argument("--backend", choices=["enttec_pro", "artnet", "null"])
    p.add_argument("--port")
    p.add_argument("--host")
    p.add_argument("--channel", type=int)
    p.add_argument("--value", type=int, default=255)
    p.add_argument("--sweep", nargs=2, type=int, metavar=("DESDE", "HASTA"))
    p.add_argument("--hold", type=float, default=2.0)
    p.add_argument("--blackout", action="store_true")
    a = p.parse_args()

    if a.list:
        for path in sorted(glob.glob("/dev/tty.usbserial*") + glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/ttyUSB*")):
            print(path)
        return

    backend = make_backend(a, load_dmx_cfg())
    u = DmxUniverse()

    def push(seconds):
        # El USB Pro necesita frames continuos; mandamos ~30 por segundo.
        end = time.time() + seconds
        while True:
            backend.send(u.frame)
            if time.time() >= end:
                break
            time.sleep(1 / 30)

    try:
        if a.blackout:
            u.blackout()
            push(0.5)
            print("blackout")
        elif a.sweep:
            for ch in range(a.sweep[0], a.sweep[1] + 1):
                u.blackout()
                u.set(ch, a.value)
                print(f"canal {ch} = {a.value}", flush=True)
                push(a.hold)
            u.blackout()
            push(0.3)
        elif a.channel:
            u.set(a.channel, a.value)
            print(f"canal {a.channel} = {a.value}")
            push(a.hold if a.hold > 0 else 0.5)
        else:
            p.print_help()
    finally:
        backend.close()


if __name__ == "__main__":
    main()
