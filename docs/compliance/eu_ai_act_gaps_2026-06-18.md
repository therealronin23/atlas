# Atlas — Brechas Reales EU AI Act + GDPR (2026-06-18)

Origen: revisión colaborativa del export de Gemini (2026-06-17). Las afirmaciones de
Gemini se contrastaron con el código y los ADRs antes de incluirlas. Solo aparecen
aquí los gaps verificados, no los puntos que Gemini marcó como problemas y que ya
estaban resueltos en el código.

---

## GAP-1 — GDPR Art. 17 vs. Merkle append-only

**Reglamento:** GDPR Art. 17 (derecho a la supresión / "derecho al olvido").

**Tensión:** El árbol Merkle es append-only por diseño. Si `InspectionRecord` almacena
el prompt original del usuario o cualquier metadato identificatorio en texto claro
dentro del árbol, es matemáticamente imposible borrar ese nodo sin invalidar la raíz
criptográfica y comprometer todos los demás registros.

**Estado actual:** `InspectionRecord` (en `client_cosign.py`) almacena `task_id`,
`session_id`, `seq`, y el hash de la solicitud — pero el hash se calcula sobre el
`CosignedRequest.payload` serializado, que puede contener el prompt del usuario.
El árbol puede contener indirectamente datos personales a través del hash si el payload
no está separado del ID personal.

**Solución requerida (crypto-shredding):**
El árbol Merkle NUNCA debe contener datos en claro ni hashes directamente vinculados
a datos personales irrecuperables. El patrón correcto:

```python
# En lugar de: leaf = SHA-256(payload_bytes)
# Hacer:
salt = os.urandom(32)          # único por petición
leaf = SHA-256(salt || payload_bytes)
# Almacenar salt en tabla relacional separada (borrable)
# El árbol contiene solo el hash — con salt destruido, el contenido es irrecuperable
```

Destruir el `salt` de la base de datos relacional hace el contenido matemáticamente
irrecuperable, pero la cadena Merkle permanece intacta (los demás registros siguen
siendo válidos).

**Impacto:** Sin esto, Atlas no puede ofrecer conformidad GDPR Art. 17 a desplegadores
en la UE. Bloquea la comercialización en mercado europeo.

**Prioridad:** CRÍTICA antes de producción.

---

## GAP-2 — Art. 26 (Deployers) — Sin Read-API pública para terceros

**Reglamento:** EU AI Act Art. 26 — los "desplegadores" que usan un sistema de IA
GPAI deben poder monitorizar la operación del sistema.

**Estado actual:** El `TransparencyLog` y los árboles Merkle existen y son
criptográficamente sólidos, pero son internos. No existe ningún endpoint, API o
interfaz que permita a una empresa integradora:
- Consultar los `InspectionRecord` de su propio tráfico
- Obtener `inclusion_proof` para un `seq` específico
- Exportar los STHs para integrarlos en sus propios SIEM

**Solución requerida:**
```
GET /api/v1/log/entries?session_id=<id>&from_seq=0&to_seq=100
GET /api/v1/log/inclusion_proof?leaf_index=<n>
GET /api/v1/log/sth/latest
```
El acceso debe ser autenticado (por `session_id` / API key del desplegador) y
scoped — un desplegador solo ve SU tráfico, no el de otros.

**Impacto:** Sin esto, los desplegadores no pueden cumplir Art. 26 por su cuenta.
Atlas garantiza transparencia interna pero no externa; el objetivo de "jaula de
cumplimiento para GPAI" queda incompleto.

**Prioridad:** Alta antes de cualquier despliegue B2B.

---

## GAP-3 — Art. 11 + Anexo IV — ADRs ≠ Technical File

**Reglamento:** EU AI Act Art. 11 — el proveedor debe mantener documentación técnica
según el Anexo IV antes de la puesta en el mercado.

**Estado actual:** Los ADRs (051, 053, 054, 055) documentan decisiones de
arquitectura. Un ADR no es un "Technical File" del Anexo IV. El Anexo IV exige:
- Descripción funcional del sistema y su finalidad prevista
- Manual de usuario y destinatarios previstos
- Métricas de rendimiento del sistema (falsos positivos/negativos del ContentFilter,
  latencia del Decider, tasa de detección de la Membrane)
- Descripción de limitaciones conocidas
- Descripción del proceso de supervisión post-comercialización

**Solución requerida:**
Crear `docs/technical_file_annex_iv.md` siguiendo la estructura del Anexo IV.
Los ADRs son la fuente de verdad técnica; el Technical File es la traducción
al formato que requiere el regulador. Las métricas requieren tests de evaluación
reales (no solo tests unitarios).

**Impacto:** Sin este documento, Atlas no puede ser puesto en el mercado dentro
de la UE bajo el régimen del EU AI Act.

**Prioridad:** Media (necesario antes de comercialización, no bloqueante para
desarrollo técnico).

---

## GAP-4 — KYC Interface en Membrane

**Reglamento:** Requisitos implícitos de controles de exportación (OFAC, regímenes
de sanciones), relevantes si Atlas procesa tráfico internacional.

**Estado actual:** El §6.5 del paper documenta honestamente que la geolocalización y
los controles de exportación están fuera del alcance técnico de Atlas y se delegan al
ámbito legal. Sin embargo, no existe ningún punto de extensión en `Membrane` que
permita a un operador inyectar una prueba de KYC externa.

**Solución requerida:**
Añadir a `Membrane.protect()` un parámetro opcional `kyc_proof: bytes | None = None`.
Si el operador tiene integración con un proveedor de KYC (Onfido, Sumsub), puede
pasar el token firmado; `Membrane` lo registra en el `InspectionRecord` como metadato.
Si el sistema está configurado para requerir KYC (`require_kyc=True` en governance)
y el proof es None, la Membrane rechaza.

**Impacto:** Permite a desplegadores cumplir controles de exportación sin que Atlas
asuma la responsabilidad del KYC. Habilita el caso de uso enterprise/B2B global.

**Prioridad:** Baja (diseño limpio, no urgente).

---

## Puntos que Gemini marcó como problemas pero que YA ESTÁN RESUELTOS

| Claim de Gemini | Realidad |
|---|---|
| "Demo usa HMAC no Ed25519" | El código usa `Ed25519PrivateKey` vía `cryptography`. El README estaba desactualizado. |
| "Split-view no cerrado = Art. 12 roto" | El paper §6 lo declara honestamente como límite. OSM-031 (WitnessNetwork) está implementado. |
| "Suite de seguridad no conectada al Decider" | ADR-054 cableado; la Membrane usa ContentFilter + ASTGuard. |
| "Git dirty invalida reproducibilidad" | Commit A/B/C (2026-06-18) limpió todo el backlog. |
| "ASTGuard bypasseable" | SEC-5 degradó a lint; ADR-055 define el jail real. |
| "Model drift no detectado" | OSM-054 + BehavioralMonitor con canary prompts implementado. |

---

## Próximos pasos por prioridad

1. **CRÍTICO (GAP-1):** Diseñar el esquema de crypto-shredding para `InspectionRecord`.
   Requiere ADR o extensión de ADR-053.
2. **Alta (GAP-2):** Diseñar Read-API del TransparencyLog. Requiere nuevo ADR o slice
   de ADR-053.
3. **Media (GAP-3):** Crear `docs/technical_file_annex_iv.md` esqueleto.
4. **Baja (GAP-4):** Añadir `kyc_proof` a `Membrane.protect()`.
