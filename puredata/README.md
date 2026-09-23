# Puente con tu prototipo de Pure Data (opcional)

El cerebro de AVI está en Python para poder probarlo en cloud. Si quieres reutilizar tu
prototipo de Pd como analizador, haz que envíe OSC al cerebro:

- `/pd/band/{sub,kick,lowmid,mid,highmid,high}` float 0–1
- `/pd/onset/{banda}` 1 en cada golpe

En Pd: `[oscformat pd band kick]` → `[netsend -u -b]` conectado a `127.0.0.1 9100`.
El cerebro podrá usar esa fuente en lugar de su propio análisis (se añade en F1).
