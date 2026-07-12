# 12 — Governance and Gates

## Objetivo

Atlas debe ser potente, pero controlable. Los Gates impiden que la autonomía se convierta en riesgo.

## Gates

### Gate 0 — Vision Gate

Comprueba que una nueva feature no convierte Atlas en chat/dashboard/IDE genérico.

### Gate 1 — Event Gate

Ningún cambio entra si no emite eventos compatibles con Event Canon.

### Gate 2 — Graph Gate

Toda entidad relevante debe proyectarse en grafo o timeline.

### Gate 3 — Memory Gate

Toda memoria nueva debe tener fuente, confianza y política de caducidad/revisión.

### Gate 4 — Adapter Gate

Todo adapter debe declarar permisos, riesgo, sandbox, outputs y failure modes.

### Gate 5 — Human Approval Gate

Acciones medium/high/critical requieren aprobación según política.

### Gate 6 — Audit Gate

Acciones relevantes generan audit.logged y, cuando aplique, Merkle hash.

### Gate 7 — Security Gate

Operaciones con filesystem, shell, red, credenciales o publicación externa requieren sandbox/permisos.

### Gate 8 — UX Gate

Toda nueva vista debe respetar visual grammar, motion grammar y máximo tres focos visuales.

### Gate 9 — Release Gate

Una fase solo se considera completa si cumple criterios verificables, no si “se ve bien”.

## Política de riesgo

```text
none      = lectura local sin efectos
low       = análisis, memoria, visualización
medium    = cambios locales reversibles
high      = escritura en repos, ejecución shell, llamadas externas
critical  = credenciales, producción, pagos, borrado destructivo
```
