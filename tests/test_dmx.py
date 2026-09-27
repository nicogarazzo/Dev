import pytest

from avi.outputs.dmx import (
    DmxUniverse,
    NullBackend,
    artnet_packet,
    backend_from_config,
    enttec_packet,
)


def test_universe_set_get_and_blackout():
    u = DmxUniverse()
    u.set(1, 255)
    u.set(512, 300)  # se recorta a 255
    u.set(9, -5)  # se recorta a 0
    assert u.get(1) == 255 and u.get(512) == 255 and u.get(9) == 0
    assert len(u.frame) == 512
    u.blackout()
    assert u.frame == bytes(512)


def test_universe_rejects_out_of_range_channel():
    u = DmxUniverse()
    with pytest.raises(ValueError):
        u.set(0, 1)
    with pytest.raises(ValueError):
        u.set(513, 1)


def test_enttec_packet_layout():
    frame = bytes([10, 20, 30]) + bytes(509)
    pkt = enttec_packet(frame)
    assert pkt[0] == 0x7E and pkt[-1] == 0xE7
    assert pkt[1] == 6  # label Output Only Send DMX
    length = pkt[2] | (pkt[3] << 8)
    assert length == 513  # start code + 512 canales
    assert pkt[4] == 0  # start code
    assert pkt[5:8] == bytes([10, 20, 30])
    assert len(pkt) == 4 + 513 + 1


def test_enttec_packet_pads_short_frames():
    pkt = enttec_packet(bytes([1]))
    length = pkt[2] | (pkt[3] << 8)
    assert length >= 25


def test_artnet_packet_layout():
    frame = bytes([1, 2, 3]) + bytes(509)
    pkt = artnet_packet(frame, universe=3, sequence=7)
    assert pkt[:8] == b"Art-Net\x00"
    assert pkt[8:10] == b"\x00\x50"  # OpDmx little endian
    assert pkt[10:12] == b"\x00\x0e"  # protocolo 14 big endian
    assert pkt[12] == 7  # secuencia
    assert pkt[14:16] == b"\x03\x00"  # universo little endian
    assert pkt[16:18] == b"\x02\x00"  # 512 bytes big endian
    assert pkt[18:21] == bytes([1, 2, 3])
    assert len(pkt) == 18 + 512


def test_artnet_packet_even_length():
    pkt = artnet_packet(bytes([9, 9, 9]))
    assert (pkt[16] << 8 | pkt[17]) == 4


def test_null_backend_from_config():
    b = backend_from_config({"backend": "null"})
    assert isinstance(b, NullBackend)
    u = DmxUniverse()
    u.set(5, 128)
    b.send(u.frame)
    assert b.sent == 1 and b.last[4] == 128
    with pytest.raises(ValueError):
        backend_from_config({"backend": "otro"})
