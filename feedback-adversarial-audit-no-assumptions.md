# Feedback — adversarial-audit-no-assumptions

- **Origen:** instrucción explícita y reiterada del operador, 2026-07-16.
- **Preferencia:** en auditorías completas, actuar con autonomía dentro del
  alcance, aplicar criterio técnico propio, investigar incertidumbres y
  reparar los hallazgos en vez de limitarse a enumerarlos.
- **Método obligatorio:** preflight factual, tronco/grafo estructural primero,
  Graphify y GraphRAG cuando aporten evidencia, pre-mortem antes de cambios de
  riesgo, tests de regresión, revisión adversarial y post-mortem.
- **Regla de honestidad:** no convertir documentos, variables de entorno,
  mocks ni pruebas aisladas en evidencia de un servicio vivo. Distinguir
  explícitamente diseño, configuración, contrato probado y verificación viva.
- **Evidencia de transcript:** una frase del modelo que afirma haber llamado
  una herramienta no sustituye el evento `tool_use`. El verificador debe
  comprobar nombre, argumentos y orden de la llamada real; ante evidencia
  incompleta, el harness puede pedir que continúe pero nunca inyectar eventos
  para mejorar la nota.
- **Límite:** la autonomía no autoriza saltarse gobierno, instalar terceros sin
  la decisión requerida, inventar hechos, modificar `config/governance.json`
  ni realizar efectos externos materialmente distintos del objetivo.
