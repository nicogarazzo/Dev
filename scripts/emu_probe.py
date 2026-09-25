"""Sondeo de la interfaz EMU MIDI->DMX (fase L2).

Envía un mensaje MIDI a la vez para descubrir cómo la EMU traduce MIDI a canales DMX.

    python scripts/emu_probe.py --list
    python scripts/emu_probe.py --mode note --number 0 --value 127 --hold 2
    python scripts/emu_probe.py --mode cc --number 1 --value 64 --hold 0   # deja el valor puesto
    python scripts/emu_probe.py --blackout --count 32                      # apaga notas/CC 0..31
"""
import argparse
import time
from pathlib import Path

import mido
import yaml

ROOT = Path(__file__).resolve().parents[1]


def default_port():
    local = ROOT / "config" / "local.yaml"
    if local.exists():
        return (yaml.safe_load(local.read_text()) or {}).get("emu_midi_port")
    return None


def send(out, mode, channel, number, value):
    if mode == "note":
        if value > 0:
            out.send(mido.Message("note_on", channel=channel, note=number, velocity=value))
        else:
            out.send(mido.Message("note_off", channel=channel, note=number, velocity=0))
    else:
        out.send(mido.Message("control_change", channel=channel, control=number, value=value))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--list", action="store_true", help="lista puertos MIDI de salida")
    p.add_argument("--port", default=None, help="puerto de la EMU (por defecto config/local.yaml)")
    p.add_argument("--mode", choices=["note", "cc"], default="note")
    p.add_argument("--channel", type=int, default=1, help="canal MIDI 1-16")
    p.add_argument("--number", type=int, default=0, help="nota o número de CC 0-127")
    p.add_argument("--value", type=int, default=127, help="velocity o valor 0-127")
    p.add_argument("--hold", type=float, default=2.0, help="segundos antes de soltar; 0 = no soltar")
    p.add_argument("--blackout", action="store_true", help="pone a 0 notas/CC 0..count-1")
    p.add_argument("--count", type=int, default=32)
    a = p.parse_args()

    if a.list:
        for name in mido.get_output_names():
            print(name)
        return

    port = a.port or default_port()
    if not port:
        raise SystemExit("Falta --port o emu_midi_port en config/local.yaml")
    ch = a.channel - 1
    with mido.open_output(port) as out:
        if a.blackout:
            for n in range(a.count):
                for mode in ("note", "cc"):
                    send(out, mode, ch, n, 0)
            print(f"blackout 0..{a.count - 1} en canal {a.channel}")
            return
        send(out, a.mode, ch, a.number, a.value)
        print(f"{a.mode} ch{a.channel} #{a.number} = {a.value}")
        if a.hold > 0:
            time.sleep(a.hold)
            send(out, a.mode, ch, a.number, 0)


if __name__ == "__main__":
    main()
