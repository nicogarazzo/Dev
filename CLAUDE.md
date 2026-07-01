# Fiverr Posting Planner — Oficina

Este repositorio es la "oficina" de trabajo para planear y ejecutar la
estrategia de publicaciones en Fiverr para vender servicios freelance.

No es una aplicación de software: es un espacio de trabajo con subagentes
especializados (`.claude/agents/`) y templates (`templates/`) que ayudan a
investigar el mercado, redactar gigs, planear un calendario de contenido y
analizar resultados.

## Subagentes disponibles

- `fiverr-market-researcher`: investiga categoría, competencia, precios y
  keywords antes de crear o reposicionar un gig.
- `fiverr-gig-copywriter`: redacta o mejora título, descripción, paquetes
  (Basic/Standard/Premium), FAQ y tags de búsqueda del gig.
- `fiverr-content-calendar-planner`: arma y mantiene el calendario de
  publicaciones/promoción (redes sociales, Buyer Requests, foro, refresh
  de gigs).
- `fiverr-performance-analyst`: analiza métricas que el usuario pega
  (impresiones, clics, conversión, rating) y sugiere ajustes concretos.

Invocá cada uno con el Agent tool usando su `name` como `subagent_type`,
según la etapa en la que esté el usuario (investigación → copy →
calendario → análisis, en ese orden recomendado, pero no obligatorio).

## Estructura

- `templates/`: plantillas reutilizables (brief de gig, descripción de
  gig, calendario de contenido).
- `content-calendar/`: calendarios de publicación generados, uno por mes
  (`YYYY-MM.md`).
- `gigs/`: borradores y versiones de gigs (título, descripción, tags,
  paquetes) por servicio.

## Convenciones

- El plan y el calendario se documentan en español (idioma del usuario),
  pero el copy final del gig se escribe en inglés salvo que el usuario
  pida explícitamente otro idioma, porque la mayoría de compradores en
  Fiverr buscan en inglés.
- No incluir en el copy de gigs nada que viole los Términos de Servicio de
  Fiverr (sin datos de contacto externos, sin pedir pagos fuera de la
  plataforma, sin comparar precios con la competencia por nombre).
