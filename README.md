# AVI

Un solo cerebro que escucha la música y dirige, de forma autónoma, las luces
(MIDI → EMU → DMX) y los visuales (TouchDesigner / Resolume) con los mismos colores y el mismo pulso.
Los filtros son adaptativos (cada instrumento se rastrea en el espectrograma) y el hardware se configura desde una UI web local.

- Plan completo: [`docs/PLAN_MVP.md`](docs/PLAN_MVP.md)
- Prompts para tu LLM local: [`docs/prompts_llm_local/`](docs/prompts_llm_local/)

| Carpeta | Qué va ahí | Fase |
|---|---|---|
| `avi/audio` | Análisis adaptativo por instrumento | F1 |
| `avi/brain` | Secciones, escenas, paleta → `ShowState` | F2 |
| `avi/patch` | Perfiles, fixtures, grupos con delay, salidas DMX | F3 |
| `avi/outputs` | ShowState → patch (luces) y OSC (TouchDesigner, Resolume) | F3 |
| `avi/ui` | UI web local: configurar, probar y monitorear hardware | F4 |
| `avi/control` | Controlador MIDI de entrada (overrides) | F5 |
| `touchdesigner/` | Script que construye la red de TD | F5 |
| `resolume/` | Notas de integración con Resolume | L5 |
| `puredata/` | Puente opcional para tu prototipo Pd | — |
| `config/` | Bandas, luces y escenas (YAML) | — |

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
