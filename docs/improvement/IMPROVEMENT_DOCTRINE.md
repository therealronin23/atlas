# IMPROVEMENT_DOCTRINE — Atlas estudia, destila y reconstruye

## Frase fundacional

Atlas no copia herramientas. Atlas estudia sistemas, destila primitivas,
identifica límites y reconstruye versiones superiores bajo una arquitectura
soberana, auditable, extensible y viva. Nada entra por moda; entra si puede
ser una primitiva superior en al menos una dimensión (transparencia,
auditabilidad, soberanía, seguridad, extensibilidad, memoria, comprensión
visual, recuperación, utilidad a largo plazo).

## Proceso

SOURCE → PRIMITIVE → LIMITATION → ATLAS REINTERPRETATION → SUPERIORITY TEST →
IMPLEMENTATION PATH. Para repos: ficha + licencia/actividad/riesgo + decisión
observe / wrap / fork / nativize / reject (fork solo con las 6 condiciones del
master prompt §8).

## El motor YA existe — no duplicarlo

Este doc documenta el pipeline REAL del repo, no crea uno paralelo:

1. **Investigación abierta autónoma**: TopicExpander (128 hallazgos/noche
   verificados, arXiv incluido) — descubrimiento, no lista fija de fuentes
   (requisito explícito de la visión: serendipia sistematizada).
2. **Digestión**: `research_digest` → candidatos de catálogo deterministas,
   dedupe fail-closed, status siempre 'candidato' (commit e10c5bcc, cableado
   al tick diario).
3. **Triage + ingesta**: informes → docs/inbox → triage → memoria/RAG con
   recall e2e verificado.
4. **Absorción**: manía `adopt-real-not-shell` — descargar→aislar→diseccionar→
   envolver (ejemplos reales: Crawl4AI, Stirling PDF, Playwright MCP,
   disección Graphiti/Zep 2026-07-10).

## Registries

`PRODUCT/PAPER/REPO_PRIMITIVES_REGISTRY.md` y `SOTA_REGISTRY.md` nacen como
SALIDAS del pipeline (digestión→candidatos), no como tablas manuales muertas.
Primera entrada real de cada registry: cuando el pipeline la produzca —
crearlas vacías hoy sería cascarón (anti-patrón declarado §25).
