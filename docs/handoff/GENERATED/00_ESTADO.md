<!-- GENERADO por atlas handoff 2026-08-01T08:01:38.683458+00:00 — NO EDITAR A MANO; regenerar con: atlas handoff -->

## WHERE

- **2026-08-01 (recalibración) — el operador retó mi confianza ("¿seguro que
  Atlas absorbió todo de Hermes?") y tenía razón: encontré un drift real de
  2 MESES en la config de permisos viva del daemon.**
  **La sobreafirmación que corrijo**: cerré LangGraph diciendo "la matriz de
  absorción queda completa" apoyándome en una auditoría de julio (2-jul),
  sin re-verificar en fresco. Hoy mismo, al leer `approval.py` de Hermes de
  verdad (3928 líneas) resultó mucho más sofisticado que el resumen de esa
  auditoría — señal de que el resto del resumen probablemente también
  infravalora lo que hay. No hay base para "todo absorbido".
  **La comparación real, no la del documento**: el modelo de Hermes es
  blocklist por patrones en 5 capas (hardline/dangerous/tirith AST/
  user-deny/sudo-guard) sobre comandos de shell libres — necesario porque
  actúa sobre el host real sin jail. El de Atlas es allowlist + jail
  estructural (BwrapJail) — default-deny, más simple, en principio más
  seguro por diseño, pero **repartido en al menos 3 ficheros pequeños sin
  relación evidente entre sí** (`router/classifier.py` 37 patrones sobre
  texto de tarea, `security/generated_code_policy.py` sobre código
  generado, `governance/permission_profile.py` sobre shell real) — nada
  parecido a un módulo único, auditado y con 1555 líneas de tests propios
  como el de Hermes.
  **El hallazgo real, no hipotético**: verificando la allowlist de shell de
  Atlas en vivo, `pwd` se rechazó con "no está en la allowlist" pese a estar
  en `config/permissions.yaml` del repo. Causa: el daemon lee
  `~/atlas/config/permissions.yaml` (copia de workspace), que
  `orchestrator.py:2619` sólo copia **si no existe** — nunca resincroniza.
  Esa copia llevaba congelada desde el **23 de mayo**; el repo se actualizó
  5 veces desde entonces (última el 16-jul, `5da5f5f`). **El daemon ha
  corrido DOS MESES con una allowlist de sólo 3 comandos cuando el repo
  autoriza 20+.** Sincronizado a mano (sin pérdida: el diff confirma que la
  copia vieja no tenía personalizaciones, sólo faltaba). El MECANISMO que
  causó el drift sigue intacto — cualquier mejora futura a
  `permissions.yaml`/`governance.json` volverá a quedarse fuera en silencio
  hasta que alguien lo note. Delegado como tarea: decidir sincronización
  real (hash/mtime al arrancar, leer del repo directo, o tick de
  mantenimiento) — y comprobar si `governance.json` tiene el mismo problema.
  **Conclusión honesta para el operador**: no, no estoy seguro de que Atlas
  absorbiera todo de Hermes. Una re-auditoría fresca y completa (no la de
  julio) es trabajo real, no hecho hoy.
