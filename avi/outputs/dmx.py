"""Salida DMX directa, sin pasar por el software EMU.

Un DmxUniverse guarda los 512 canales (valores 0-255, canal 1 = índice 0) y un
backend los manda al hardware. Backends:

- EnttecProBackend: ENTTEC DMX USB Pro / Mk2 (y clones "Pro compatible") por
  puerto serie con el protocolo del widget (label 6 = Output Only Send DMX).
- ArtNetBackend: cualquier nodo Art-Net (ODE, EMU Hardware, nodos chinos) por UDP.
- NullBackend: para tests y para correr el cerebro sin luces.

Todo lo que arma bytes está separado del I/O para poder probarlo sin hardware.
"""
from __future__ import annotations

import socket
import struct

DMX_CHANNELS = 512

# Protocolo ENTTEC DMX USB Pro (API 1.44)
ENTTEC_SOM = 0x7E
ENTTEC_EOM = 0xE7
ENTTEC_LABEL_SEND_DMX = 6

ARTNET_PORT = 6454
ARTNET_OPDMX = 0x5000


def enttec_packet(channels: bytes, label: int = ENTTEC_LABEL_SEND_DMX) -> bytes:
    """Arma un mensaje del widget. Para label 6 el payload es start code 0 + canales."""
    payload = bytes([0]) + bytes(channels)
    if len(payload) < 25:  # el widget exige al menos 24 canales
        payload = payload + bytes(25 - len(payload))
    if len(payload) > DMX_CHANNELS + 1:
        raise ValueError("máximo 512 canales")
    length = len(payload)
    return (
        bytes([ENTTEC_SOM, label, length & 0xFF, (length >> 8) & 0xFF])
        + payload
        + bytes([ENTTEC_EOM])
    )


def artnet_packet(channels: bytes, universe: int = 0, sequence: int = 0) -> bytes:
    """Arma un ArtDmx (OpDmx 0x5000, protocolo 14). El largo de datos debe ser par."""
    data = bytes(channels)
    if len(data) % 2:
        data += b"\x00"
    if len(data) > DMX_CHANNELS:
        raise ValueError("máximo 512 canales")
    return (
        b"Art-Net\x00"
        + struct.pack("<H", ARTNET_OPDMX)
        + struct.pack(">H", 14)
        + bytes([sequence & 0xFF, 0])
        + struct.pack("<H", universe & 0x7FFF)
        + struct.pack(">H", len(data))
        + data
    )


class DmxUniverse:
    """512 canales. set(canal_1_based, valor) y luego backend.send(universe.frame)."""

    def __init__(self) -> None:
        self._data = bytearray(DMX_CHANNELS)

    def set(self, channel: int, value: int) -> None:
        if not 1 <= channel <= DMX_CHANNELS:
            raise ValueError(f"canal DMX fuera de rango: {channel}")
        self._data[channel - 1] = max(0, min(255, int(value)))

    def get(self, channel: int) -> int:
        return self._data[channel - 1]

    def blackout(self) -> None:
        self._data[:] = bytes(DMX_CHANNELS)

    @property
    def frame(self) -> bytes:
        return bytes(self._data)


class NullBackend:
    def __init__(self) -> None:
        self.last: bytes | None = None
        self.sent = 0

    def send(self, frame: bytes) -> None:
        self.last = frame
        self.sent += 1

    def close(self) -> None:
        pass


class EnttecProBackend:
    """ENTTEC DMX USB Pro por serial. Requiere pyserial. En macOS el puerto es
    /dev/tty.usbserial-EN* (o /dev/cu.usbserial-*)."""

    def __init__(self, port: str, baudrate: int = 57600) -> None:
        import serial  # pyserial, import perezoso para no exigirlo en tests

        self._ser = serial.Serial(port, baudrate=baudrate, timeout=1)

    def send(self, frame: bytes) -> None:
        self._ser.write(enttec_packet(frame))

    def close(self) -> None:
        self._ser.close()


class ArtNetBackend:
    def __init__(self, host: str = "255.255.255.255", universe: int = 0, port: int = ARTNET_PORT) -> None:
        self._addr = (host, port)
        self._universe = universe
        self._seq = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if host.endswith(".255"):
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def send(self, frame: bytes) -> None:
        self._seq = (self._seq % 255) + 1  # 1..255, 0 significa "sin secuencia"
        self._sock.sendto(artnet_packet(frame, self._universe, self._seq), self._addr)

    def close(self) -> None:
        self._sock.close()


def backend_from_config(cfg: dict):
    """cfg = bloque `dmx:` de config/local.yaml o fixtures.yaml."""
    kind = (cfg or {}).get("backend", "null")
    if kind == "enttec_pro":
        return EnttecProBackend(cfg["serial_port"])
    if kind == "artnet":
        return ArtNetBackend(cfg.get("host", "255.255.255.255"), int(cfg.get("universe", 0)))
    if kind == "null":
        return NullBackend()
    raise ValueError(f"backend DMX desconocido: {kind}")
