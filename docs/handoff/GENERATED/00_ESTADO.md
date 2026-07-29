<!-- GENERADO por atlas handoff 2026-07-29T12:23:37.192595+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-07-29 — convergencia publicada y sucesión preparada desde
  `atlas-core/main`.** El trabajo versionado de la candidata definitiva está
  integrado por fast-forward y publicado: `main`, `origin/main` y
  `codex/atlas-definitive-integration-20260728-230000` coincidían en
  `0fea4c6c6ebac26a3d9420e6b099023d47644863` antes de este cierre de
  continuidad. El estado vivo previo del checkout quedó preservado y publicado
  en `recovery/pre-definitive-live-20260729@4784a4f`; el ZIP R2.1 sigue
  deliberadamente fuera de Git. El bundle completo verificado está en
  `/home/ronin/proyectos/atlas-definitive-backup/atlas-definitive-convergence-20260729-0fea4c6.bundle`
  (SHA-256
  `b166405341465ecbdcdfbe5dcb800d41f9095d351058c4b0bc07ddf724834b8f`).
  `atlas reality` observa el grafo en `c95038c` y por tanto `STALE`, navegador
  degradado por Playwright ausente, Hermes mock/no configurado y F2.6 `due`
  por siete ADR nuevos; no son claims live. La suite completa más reciente
  del informe de entrega pertenece a `fac6bca`, no a la cabeza final; los
  hardenings posteriores tienen pruebas focales y necesitan un pase integral
  fresco. Se corrigió además la autorreferencia de `atlas handoff --check`: el
  commit que contiene exclusivamente el pack generado ya no lo invalida, pero
  cualquier commit vacío, ajeno o mezclado sigue marcándolo `STALE`. El
  auditor del índice excluye ahora sólo el snapshot runtime gitignorado
  `docs/audit_complete_latest.json`; el receipt versionado homónimo bajo
  `docs/audits/` continúa siendo evidencia indexada.
  **Próxima acción:** desde un clon limpio de `main`, leer
  `docs/handoff/GENERATED/00_ESTADO.md`, ejecutar `atlas reality --json`,
  atender la notificación F2.6 sin lanzarla silenciosamente, regenerar el
  grafo estructural y correr suite+mypy+UI+audit antes de aceptar la candidata;
  después continuar `ADC-WO-108`, sin abrir `ADC-WO-109/110/111` ni boundaries
  reservados hasta satisfacer sus gates.
