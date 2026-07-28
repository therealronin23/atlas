# ADR-078 — Convergencia de linajes en Atlas Engineering Workbench

- **Estado:** aceptado por el operador
- **Fecha:** 2026-07-28
- **Programas:** P00, P02, P06, P08, P09
- **Refina:** ADR-071
- **Diseño aprobado:** `docs/superpowers/specs/2026-07-28-atlas-lineage-workbench-symbiosis-design.md`

## Contexto

Atlas acumuló trabajo sustancial en `atlas-core`, Atlas IDE/Void, un
forward-port de Void, CodeOSS, Zed, dos ramas Doc0 y varios worktrees de
autoconstrucción. La topología Git no determina si ese trabajo pertenece al
producto: un clon puede ser parte del mismo linaje y un commit ancestro puede
no aportar ningún delta pendiente.

La UI web experimental demostró contratos, pero no alcanzó la UX profesional
requerida por ADR-071. Al mismo tiempo, escribir otro editor o reimplementar
capacidades maduras produciría coste sin mejorar el núcleo cognitivo.

## Decisión

1. `atlas-core` continúa siendo la única autoridad canónica de política,
   memoria, conocimiento, inferencia, planificación, ejecución, aprobación,
   auditoría y recuperación.
2. El primer producto completo será **Atlas Engineering Workbench**: una
   superficie de supervisión para misiones, revisiones, hallazgos, incidentes,
   diagnóstico, diffs y correcciones propuestas, validaciones, receipts y
   aprobaciones. El editor sirve para correcciones quirúrgicas, no para
   optimizar escritura humana continua.
3. La cadena de host desktop será:

   ```text
   CodeOSS actual
     + disciplina de build, privacidad, branding, updates y Open VSX de VSCodium
     + capacidades Atlas portadas desde Void
     + ACP y patrones compatibles asimilados desde Zed
     + contratos gobernados de Atlas Core
   ```

4. CodeOSS/VSCodium es el host; Void es donante de capacidades; Zed es donante
   ACP y de patrones. Ninguno se convierte en una autoridad Atlas paralela ni
   se fusiona entero por topología.
5. Toda capacidad se clasifica como `MOVE`, `PORT`, `WRAP`, `CONNECT`, `PIN`,
   `CLEAN_ROOM` o `REJECT`. Se reutiliza código existente antes de reescribirlo.
6. `ui/atlas-shell` permanece como `VALIDATION_HARNESS`; no es el producto
   aceptado ni la base visual obligatoria.
7. ADR-071 sigue exigiendo aplicaciones dedicadas Linux y Android. Este ADR
   selecciona el host de la Workbench desktop; no selecciona falsamente una
   implementación Android. Esa proyección se diseña cuando los contratos de
   superficie sean estables.
8. Autocompletado propio, tab completion, IntelliSense propio y una
   reimplementación de SCM, DAP o Test Explorer quedan fuera del trabajo Atlas.
9. La UI consume proyecciones y propuestas. No recibe una ruta privilegiada
   para aplicar efectos fuera de Decider, Golden Route, ColdUpdate, Merkle y
   los invariantes de sensibilidad.

## Secuencia vinculante

- **Corte 0 — candidata definitiva:** inventariar y reconciliar linajes,
  corregir divergencias comprobadas, cerrar canon y validación. No trasplantar
  todavía árboles completos de editor.
- **Corte 1 — plano interno de ingeniería:** `EngineeringFinding`,
  ReviewCoordinator, DiagnosticCoordinator, eventos, persistencia,
  Orchestrator y contratos de proyección.
- **Corte 2 — Workbench:** convergencia profesional completa sobre un upstream
  fijado, con integración amplia y progresiva de Void y asimilación relevante
  de Zed. Su alcance exacto se decidirá en su propio diseño; no se presume
  mínimo ni acotado.
- **Corte 3 — evolución:** revisión adicional, depuración distribuida,
  visualización avanzada, estética y nuevos forks admitidos por el mismo
  contrato.

## Invariantes y licencias

- Código externo permanece no confiable hasta procedencia, licencia,
  supply-chain, análisis y pruebas de contrato.
- No se copia código incompatible entre superficies MIT/Apache y GPL sin una
  decisión constitucional de licencia.
- Open VSX o fuentes compatibles sustituyen cualquier supuesto acceso al
  Visual Studio Marketplace.
- Un bridge ausente degrada a no operativo o solo lectura; nunca ejecuta
  directamente.
- Un hallazgo propone; no aplica un patch.
- Sensibilidad alta sigue terminando en humano o denegación.

## Estado real y no afirmaciones

Esta decisión constituye `ACCEPTED_DESIGN`. No demuestra `CODE_PRESENT`,
`WIRED`, `LIVE_VERIFIED` ni `PRODUCT_ACCEPTED` para Atlas Workbench. El
forward-port de Void queda preservado como fuente de port; CodeOSS/VSCodium
como baseline de host; Zed como donante; y `atlas-shell` como arnés.

## Rollback

Cada port se limita a seams Atlas identificables y conserva el último baseline
compilable fijado por SHA. Si un port deriva o rompe contratos, se desactiva o
revierte el seam sin mover autoridades fuera de `atlas-core`. Revertir este ADR
restaura la pregunta de host/producto, pero no borra linajes ni evidencia.
