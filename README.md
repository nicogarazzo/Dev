# Fiverr Posting Planner

Oficina de trabajo (subagentes de Claude Code) para planear y ejecutar la
venta de servicios en Fiverr: investigación de mercado, redacción de
gigs, calendario de publicaciones y análisis de performance.

Ver [`CLAUDE.md`](./CLAUDE.md) para el detalle de cada subagente y la
estructura del repo.

## Flujo recomendado

1. **Investigar** el servicio con `fiverr-market-researcher` →
   `gigs/<servicio>/brief.md`.
2. **Redactar** el gig con `fiverr-gig-copywriter` →
   `gigs/<servicio>/gig-copy.md`.
3. **Planear** la promoción con `fiverr-content-calendar-planner` →
   `content-calendar/YYYY-MM.md`.
4. **Analizar** resultados con `fiverr-performance-analyst` y volver al
   paso que corresponda según el diagnóstico.

## Estructura

```
.claude/agents/          subagentes especializados
templates/                plantillas de brief, copy y calendario
gigs/<servicio>/           brief y copy final por servicio
content-calendar/          calendarios mensuales generados
```
