# F2 — Cerebro: secciones, escenas y paleta

Código en `avi/brain/`, parámetros en `config/show.yaml` (o `config/show.example.yaml`),
tests en `tests/test_brain.py`.

## Cómo se usa

```bash
avi synth out/show.wav --sections   # ~90 s con verdad conocida: calm → build → drop → break → drop
avi show out/show.wav               # análisis + cerebro → out/show.show.json + resumen en pantalla
avi live --brain                    # en vivo: sección, escena y paleta al lado de los niveles
avi live --brain --json             # un ShowState JSON por frame, para otro proceso
```

Desde Python:

```python
from avi.audio import Analyzer
from avi.brain import Brain

an, brain = Analyzer(), Brain()             # Brain() lee config/show.yaml o el ejemplo
for frame in an.process(bloque):
    state = brain.update(frame)             # un ShowState por AudioFrame
    state.section, state.scene, state.palette, state.lights["front"], state.visuals
    payload = state.to_dict()               # JSON del plan (§3)

brain.set_override(scene=2, palette="neon") # F5: controlador MIDI
brain.set_override(blackout=True)
brain.release()                             # vuelve a lo que el cerebro eligió mientras tanto
```

## El `ShowState` (un solo estado para luces y visuales)

`state.to_dict()` = todo el `AudioFrame` de F1 (`t`, `bpm`, `beat`, `bar`, `phrase_pos`,
`instruments`, `energy`…) **más** lo que decide el cerebro:

| Campo | Qué es |
|---|---|
| `section`, `section_bars` | `calm` / `build` / `drop` / `break` y cuántos compases lleva |
| `scene`, `scene_name`, `td_scene`, `td_clip` | Escena de `config/show.yaml`: índice de escena en TD y clip propio (`/avi/scene`, `/avi/clip`) |
| `palette`, `palette_name` | 3 colores RGB 0–1, ya con el cruce aplicado. Luces y TD leen **estos** |
| `lights` | Por grupo (`all`, `front`, `wave`…): `dimmer`, `rgb`, `white`, `strobe`, `chase`, `chase_step` (0–1 salvo el paso) |
| `visuals` | Por parámetro de TD del `mapping` (`zoom_pulse`, `glitch`…) 0–1, más `intensity` |
| `override` | `null` o `{scene, palette, blackout}` |
| `changes` | Solo en el frame donde cambió algo: `["section", "scene", "palette"]` |

El cerebro nunca habla de canales DMX. F3 traduce `lights` a canales con los perfiles,
y aplica el `delay_ms` de cada grupo; para `chase`, enciende el fixture
`chase_step % miembros` con nivel `chase`.

## Cómo decide

Cada frame pasa por tres piezas:

1. **Reloj de compás** (`BarClock`). Usa los beats del análisis; si no hay tempo (intro sin
   bombo) sigue contando con el último periodo conocido (120 BPM al arrancar). Así siempre
   hay compás y frase.
2. **Detector de secciones** (`SectionDetector`). Junta cada compás: golpes de bombo, golpes
   de hats + snare, volumen en dB. En cada downbeat decide:

   | Sección | Regla (por compás) |
   |---|---|
   | `drop` | Bombo denso (≥ 3 golpes) y volumen a ≤ 4 dB del compás más fuerte reciente, **y** un salto de ≥ 3 dB sobre los 4 compases previos tras un `build` o `break` (≥ 6 dB desde `calm`). Entra en el compás siguiente, sin esperar histéresis. Se mantiene mientras haya bombo y no caiga más de 8 dB |
   | `break` | Sin bombo, después de haber tenido bombo |
   | `build` | Golpes de hats + snare subiendo en los últimos 5 compases (≥ 0,5 golpes/compás y ≥ 12 % de la media), o volumen subiendo ≥ 0,6 dB/compás. Un build que ya no sube se suelta a los 16 compases |
   | `calm` | Todo lo demás |

   Histéresis: una sección nueva cuenta cuando se repite 2 compases (salvo el drop con salto).
   Si AVI arranca con la canción ya arriba, el primer drop entra sin salto.
3. **Motor de escenas** (`SceneEngine`). Cuando cambia la sección, elige una escena que la
   incluya y una de sus paletas (rota para no repetir la misma):
   - cambios cuantizados al inicio de frase (16 beats) y tras ≥ 8 compases en la escena;
   - el `drop` entra en el beat 1, sin esperar frase ni duración mínima, con la paleta en seco;
   - el resto cruza la paleta en 4 beats;
   - el override gana siempre hasta `release()`.

Las **intenciones** (`IntentEngine`) salen del `mapping` de `config/show.yaml`:
`dimmer_base` (respira con el nivel), `dimmer_flash` (salta a 1 en cada golpe y cae en
~150 ms), `hue_shift` (mueve el color del grupo del color 1 al 2 de la paleta), `white`,
`strobe` (solo en `drop`) y `chase` (cada golpe avanza un paso). El dimmer se limita por
sección: calm 0,6 · build 0,75 → 1 · drop 1 · break 0,35.

## Resultado con la canción sintética (`avi synth --sections`, 126 BPM)

| Verdad | Detectado |
|---|---|
| calm 0–15,2 s | calm 0–27,6 s (el build sintético arranca con hats suaves que el pad tapa) |
| build 15,2–30,5 s | build 27,6–31,4 s |
| drop 30,5 s | drop 31,4 s (compás siguiente) → escena `drop`, paleta `fuego` |
| break 61,0 s | break 65,9 s (histéresis de 2 compases) → escena `ambiente` en la frase siguiente |
| drop 76,2 s | drop 77,2 s → escena `drop`, paleta `neon` (rota) |

Probado también a 118, 128 y 140 BPM: misma secuencia de secciones.

## Para la UI (PR #7) y F3

- La UI puede reemplazar sus reglas provisionales usando `state.to_dict()` como cuadro:
  es un superconjunto del cuadro de F1 que ya consume.
- `section_spans(states)` devuelve `[{name, start, end}]`, el formato de `TL.sections`.
- `avi show` escribe `{sections, changes, frames}` con los `ShowState` a 30 cuadros/s.

## Límites conocidos

- El build sintético se detecta tarde porque el pad de la intro genera golpes falsos de
  hats/snare (F1) que esconden la subida. Con música real se ajusta en L3 con
  `rules.sections` en `config/show.yaml`.
- El downbeat viene de la heurística de F1: si está corrido 2 beats, las secciones también.
- No hay aún rotación de escena dentro de una sección larga.
