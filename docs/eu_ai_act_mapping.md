# Mapeado EU AI Act — Atlas Compliance Gateway

*Fecha: 2026-06-15. Estado: trabajo en curso. Sin porcentajes de cumplimiento inventados.*

Este documento mapea los artículos del Reglamento (UE) 2024/1689 (EU AI Act) que son
relevantes para el Atlas Compliance Gateway. El Gateway no es un sistema de IA de alto
riesgo en sí mismo — es una **capa de cumplimiento** alrededor de modelos frontier
clasificados como GPAI con riesgo sistémico. Por eso, la mayor parte de los artículos
de Capítulo III (high-risk obligations) aplican **como referencia de diseño**, no como
obligaciones formales directas sobre Atlas.

Estados: ✅ implementado · 🟡 parcial o diseñado sin todos los tests · ❌ pendiente / no aplica hoy

---

## Artículos núcleo (logging, transparencia, supervisión)

| Artículo | Qué exige | Estado | Evidencia / gap |
|---|---|---|---|
| **Art. 9** — Risk management system | Sistema continuo de identificación, análisis y mitigación de riesgos a lo largo del ciclo de vida | 🟡 | 4 capas L1–L4 (ADR-054) documentadas con risks R1–R5. L1/L4 completas; L2/L3 con gaps en salting real (API pura) y witnesses distribuida. |
| **Art. 11** — Technical documentation | Documentación técnica completa antes de puesta en mercado (Annex IV: descripción, diseño, tests, limitaciones) | 🟡 | ADR-051/053/054 cubren diseño e invariantes. Falta formato Annex IV regulatorio formal. |
| **Art. 12** — Automatic logging / record-keeping | Logs automáticos con marcas temporales, inputs, outputs, decisiones; tamper-resistant; mínimo 6 meses de retención | ✅ | `src/atlas/transparency/` — Merkle RFC 9162 + co-firma cliente + `detect_omission()`; secuencia monótona; diseño append-only. Estado actual verificable con `atlas reality --run-checks`; no se mantiene un conteo manual en docs. ADR-053 accepted. |
| **Art. 13** — Transparency to users | Informar al usuario de que interactúa con un sistema de IA; informar de inspecciones de contenido con causa | ✅ / 🟡 | Verificabilidad mutua: el usuario detecta omisiones de inspección unilateralmente (no requiere confiar en el operador). Gap: falta UI que informe activamente al usuario final en cada sesión. |
| **Art. 14** — Human oversight | El sistema debe poder ser monitorizado, intervenido y detenido por personas físicas; override posible | ✅ | Decider (ADR-040): `Allow \| Deny \| RequiresHuman`. Tier MEDIUM+ requiere revisión explícita (invariante I5, ADR-054). Toda promoción de regla activa pasa por PDP. |
| **Art. 15** — Accuracy, robustness, cybersecurity | Resiliencia frente a errores, fallos y ataques adversariales, incluyendo ataques a los datos de entrenamiento y modelos | 🟡 | ADR-054: 4 capas L1–L4 de defensa en profundidad. Gap: L2 (salting) degradada — Nemotron vía API externa, sin acceso a activaciones. R2 sin cerrar: ADR-049 no cableado al panel adversarial todavía. L3c (behavioral drift, Session J) implementado en log; análisis diferido. |
| **Art. 24** — Post-training model assessment | Evaluación de capacidades post-entrenamiento (sesgos, hallucinations, riesgos específicos del uso esperado) | 🟡 | ADR-054 L4 + ADR-049: ciclo continuo de lecciones + enjambre recalculando límites de riesgo. Diferido: red de witnesses distribuida para validar cambios con terceros independientes. |
| **Art. 26** — Obligations of deployers | Los desplegadores de sistemas de IA de alto riesgo deben monitorizar la operación del sistema y reportar incidentes graves a los proveedores; deben asegurarse de que se usan conforme a instrucciones | 🟡 | El log verificable (L4, ADR-053) da a los desplegadores (empresas que integran frontier models vía API) la base de evidencia per-request para monitorización real. Session J + behavioral drift detection en L3c permite identificar cambios de heurística sin reentrenamiento aparente. Gap: el desplegador necesita acceso de lectura al log que hoy no está expuesto como API pública. |

---

## Capítulo V — GPAI models (aplica a Anthropic, no a Atlas directamente)

| Artículo | Qué exige | Relevancia para Atlas |
|---|---|---|
| **Art. 50(1)** — AI-generated content marking | Outputs de IA generativa marcados como generados por IA | ❌ Fuera del alcance del Gateway. Responsabilidad del proveedor del modelo (Anthropic). |
| **Art. 52** — GPAI transparency obligations | Documentación técnica del modelo (capabilities, training data summary, energy use); publicar resumen para derechos de autor | N/A para Atlas. El Gateway no provee el modelo. |
| **Art. 53** — GPAI with systemic risk | Red-teaming, evaluación de capacidades peligrosas, reporte de incidentes graves, ciberseguridad end-to-end | 🟡 Aplica formalmente a **Anthropic** como proveedor. El Gateway contribuye: ADR-054 capa 5 + organismo de conocimiento (ADR-049) = fuente de diversidad de ataque externa que cierra el gap de auto-juego que CC++ tiene por construcción. Sin Atlas, Anthropic solo puede red-teamear con su propio tráfico. |
| **Art. 55** — Delegated acts | La Comisión puede añadir más obligaciones para systemic-risk GPAI | Seguir actualizaciones. Sin acción inmediata. |

---

## Sandboxes y gobernanza

| Artículo | Qué exige | Estado |
|---|---|---|
| **Art. 57** — AI regulatory sandboxes | Estados miembro deben tener sandboxes operativos; SMEs pueden aplicar con proceso simplificado | 🟡 AESIA (España) es la vía más directa. El núcleo de ADR-053 es exactamente lo que un sandbox necesita para testear verificabilidad mutua. Aplicación pendiente. |
| **Art. 72** — Serious incident reporting | Proveedores de GPAI con riesgo sistémico deben reportar incidentes graves | N/A para Atlas hoy. |

---

## Límites honestos (lo que NO cumplimos hoy)

Estas no son excusas — son trabajo pendiente documentado.

- **Art. 16-43 (conformity assessment, CE marking, notified bodies)**: No implementado. Requiere equipo, auditoría externa independiente, y registro en EU AI systems database. Camino de meses, no semanas.
- **KYC / binding de identidad real**: No resuelto. Crítico para los export controls que causaron el shutdown de Fable 5. Es legal y operativo, no código. Atlas no puede resolver esto solo.
- **Witness network (RFC 9162 gossip)**: Diferido. La protección split-view requiere ≥1 witness externo. Hoy el usuario detecta omisiones unilateralmente (co-firma + secuencia monótona) pero un operador malicioso puede mostrar logs distintos al regulador y al usuario sin que se detecte sin un witness externo.
- **Hardware attestation (Intel TDX / AMD SEV-SNP)**: Diferido. ADR-053 usa attestation software (HMAC). La prueba criptográfica del binario en ejecución requiere infraestructura hardware específica.
- **Auditoría externa independiente**: No realizada. El self-audit de Atlas + los tests son evidencia técnica pero no sustituyen una auditoría por tercero independiente.
- **Art. 11 / Anexo IV (Technical File)**: Hoy hay ADRs (051/053/054), que cubren diseño e invariantes pero **no son documentación regulatoria**. Falta el formato exacto del Anexo IV: descripción funcional, manual, **métricas de falsos positivos/negativos** de la inspección por causa, y limitaciones declaradas. Tarea de documentación, no arquitectónica. (Barrido Gemini 2026-06-17.)
- **GDPR Art. 17 (derecho de supresión) vs. inmutabilidad Merkle**: tensión real. El log guarda hash, no texto, pero un hash de baja entropía es reidentificable. Mitigación de diseño: crypto-shredding con salt por petición (membrana [[OSM-007]]). Choca además con la retención mínima de 6 meses del Art. 12 — tensión legal entre dos reglamentos, no resoluble solo en código. (Barrido Gemini 2026-06-17.)
- **Art. 13 — canal de transparencia al usuario**: la verificabilidad criptográfica existe en backend (`detect_omission()`), pero falta el canal/UI que la surface a un humano. Criptografía sin interfaz no es transparencia regulatoria. (Membrana OSM-041; barrido Gemini.)

---

## Posición honesta

El Atlas Compliance Gateway implementa **el mecanismo técnico más directo disponible hoy para cumplir Art. 12 y Art. 13** en el contexto de frontier models:

- Art. 12: El log Merkle con co-firma y detect_omission() es append-only, verifiable, y soporta retención indefinida.
- Art. 13: La verificabilidad mutua permite al usuario demostrar inspecciones sin causa — algo que ningún sistema en producción ofrece hoy.

Lo que falta (Art. 16-43, KYC, witnesses) es **camino de producto**, no límite arquitectónico. Los cimientos están. La certificación formal es el siguiente paso, no el primero.

---

*Referencias: Regulation (EU) 2024/1689 · RFC 9162 (Certificate Transparency) · RFC 9334 (RATS) · ADR-051/053/054 · `src/atlas/transparency/`*
