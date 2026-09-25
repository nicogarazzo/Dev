# F1 — Análisis de audio adaptativo

Código en `avi/audio/`, parámetros en `config/bands.yaml`, tests en `tests/test_audio_analysis.py`.

## Cómo se usa

```bash
pip install -e ".[dev]"
avi demo                                   # pista sintética → out/demo.wav + out/demo.json
avi analyze cancion.wav -o out/cancion.json  # timeline JSON a 30 cuadros/s
avi listen --list                          # dispositivos de audio
avi listen --device "VB-Cable"             # medidor en vivo (Ctrl+C para salir)
avi listen --device "VB-Cable" --json      # un JSON por frame, para otro proceso
```

`avi analyze` lee WAV PCM sin dependencias extra; con `pip install soundfile` también
FLAC/OGG. Para MP3: `ffmpeg -i cancion.mp3 cancion.wav`.

Desde Python:

```python
from avi.audio import Analyzer
an = Analyzer()                      # usa config/bands.yaml
for frame in an.process(bloque):     # bloque = numpy mono, cualquier tamaño
    frame.instruments["kick"].level, frame.instruments["kick"].onset, frame.bpm, frame.is_beat
```

## Qué produce cada frame (~10.7 ms a 48 kHz)

| Campo | Qué es |
|---|---|
| `instruments.{sub,kick,bass,voice,snare,hats}` | `level` 0–1, `onset` (solo transitorios), `hz` rango que está capturando ahora, `confidence` 0–1 |
| `bpm`, `beat` (1–4), `bar`, `is_beat`, `beat_phase` | Tempo y fase; `is_beat` cae en el frame del golpe (se compensa la latencia de la FFT) |
| `energy`, `energy_long` | Energía corta (~0.3 s) y larga (~8 s), 0–1. El cerebro (F2) las compara para `calm`/`build`/`drop`/`break` |
| `loudness_db`, `centroid_hz`, `brightness` | Volumen y "color" del espectro; `brightness` 0–1 sirve para elegir paleta |

Las claves de `instruments` son las mismas del `ShowState` del plan (§3).

## Cómo funciona

1. **Espectrograma en streaming**: FFT de 2048 con salto de 512 (Hann).
2. **Percusivo vs armónico**: mediana causal de los últimos 9 frames. Lo que se sostiene
   es armónico; lo nuevo, percusivo. Suman exactamente el frame original.
3. **Máscara suave**: cada bin se reparte entre rastreadores en proporción a
   huella × activación (NMF de un frame con huellas conocidas). Transitorios (`kick`,
   `snare`, `hats`) reparten la parte percusiva; tonales (`sub`, `bass`, `voice`) la
   armónica. Por eso un bajo en 110 Hz no hace pulsar al bombo aunque compartan bins.
4. **Huellas adaptativas**: se actualizan con lo capturado (en golpes para
   transitorios, en frames estables para tonales), constante de tiempo 4 s, centro
   limitado a `center_max_shift_per_s`, tirón suave al nominal, nunca fuera de `search_hz`.
5. **Confianza**: fracción de la energía de su rango que se lleva cada rastreador. Si baja
   de `min_confidence` (p. ej. en silencio), el rango reportado vuelve al nominal.
6. **Golpes**: la energía percusiva del rastreador sube, supera media + 1.5·desviación
   reciente y el 20 % de su pico, con 80 ms de periodo refractario.
7. **BPM**: autocorrelación de 8 s de la envolvente de golpes (más peso a graves), peine de
   múltiplos y prior en 120 BPM contra errores de octava; la fase se sigue con un PLL.

## Medido con audio sintético (tests)

- Bombo y bajo superpuestos: el bombo pulsa > 3× en sus golpes; el bajo varía < 25 %.
- Golpes de bombo, snare y hats: recall ≥ 90 %, precisión ≥ 90 % (tolerancia 60 ms).
- BPM exacto (± 1) a 90, 128 y 174; beats a < 30 ms del bombo.
- Un bajo en 440 Hz mueve el rango de `bass` hacia arriba sin salir de 60–500 Hz.
- ~12× más rápido que tiempo real en un solo núcleo.

## Lo que falta calibrar con música real (L3)

- Rangos `search_hz` y `min_confidence` con canciones reales vía VB-Cable (`avi listen`).
- `downbeat` (beat 1) es heurístico: elige la posición del compás con más graves.
- Latencia de detección de golpes: ~20–25 ms tras el ataque (media ventana FFT).
