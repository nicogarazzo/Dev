# Prompts para tu LLM local

Desde el 2026-09-23 las fases locales las hace Claude directamente en tu Mac por Remote Control
(hilo "Setup local AVI en Mac"). Estos prompts quedan de **respaldo** para tu LLM local.
Todos terminan con un `git push` a una rama `local/...`, para que el siguiente paso en cloud
lo use sin que copies nada a mano.

| Prompt | Cuándo | Resultado |
|---|---|---|
| `L1_setup_entorno.md` | Hecho (PR #3) | `config/local.yaml` (audio, puertos MIDI, versión de TD) |
| `L2_mapear_emu_y_luces.md` | Cuando aparezcan la interfaz ENTTEC y las luces | `config/fixtures.yaml` + `config/local.yaml → dmx:` + `docs/hardware/emu_y_luces.md` |
| `L3` calibrar rastreadores | Después de F1 | Se escribe cuando exista el analizador y el monitor |
| `L4` hardware en la UI + TouchDesigner + prueba integrada | Después de F3, F4 y F5 | Se escribe cuando existan patch, UI y el script de TD |
| `L5` Resolume (opcional) | Después de L4 | Se escribe si decides usar Resolume |
