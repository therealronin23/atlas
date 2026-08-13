# ADR-053 — Modelo de confianza y completitud del Compliance Gateway

Fecha: 2026-06-15 · Estado: **Aceptado (núcleo criptográfico); evidencia de
completitud/neutralidad PROVISIONAL** — inclusion/consistency proofs, co-firma y
comparación local están implementadas y tienen tests específicos; el estado
actual de suite/tipos se obtiene con `atlas reality --run-checks` y no se
mantiene a mano en el ADR. Diferidos: attestation de hardware real
(TDX/SEV-SNP), witnesses independientes y prueba de completitud off-path. ·
Mitiga B1+B2; **no demuestra su cierre end-to-end** (auditoría
`audit_adr051_052_premortem_2026-06-15.md`). · Contexto: ADR-051 (Compliance
Gateway), MerkleLogger (Gate F), ADR-029 (reverse-audit), ADR-040 (Decider).

> Este ADR existe porque la auditoría demostró que ADR-051 tenía la viga maestra
> rota: **Merkle prueba integridad, no completitud** (B1), y **no había operador
> neutral creíble** (B2). La versión de 2026-06-15 afirmó que aquí se cerraban
> ambos; la revalidación de 2026-08-12 conserva la decisión, pero contradice ese
> claim de cierre completo.

---

## Hechos de partida (estándares, verificados 2026-06-15)

- **RFC 9162 — Certificate Transparency v2.** Log append-only sobre Merkle;
  *consistency proofs* prueban que un estado posterior contiene íntegro al
  anterior (no se reescribió historia); *inclusion proofs* prueban que una
  entrada está. Varios clientes pueden comparar Signed Tree Heads (STH), técnica
  llamada *gossip*, pero RFC 9162 la declara investigación activa y **no la
  define**; además advierte que una vista inconsistente puede eludir sus
  mecanismos y deja el remedio fuera de alcance.
- **RFC 9334 — RATS (Remote Attestation).** Un *Attester* en enclave (Intel TDX
  → *TD Quote* firmado; AMD SEV-SNP → *attestation report* vía VCEK/VLEK)
  produce evidencia criptográfica de la medición del binario en ejecución; un
  *Verifier* la appraisa contra la medición esperada (build publicado).
  Topologías Background-Check y Passport.

---

## Decisión: tres capas, cada una atada a su estándar

### Capa 1 — Enrollment (la "firma única al aceptar")

Al darse de alta, el cliente del usuario genera un par de claves y **registra la
pública firmando el contrato** (sección 7 de ADR-051) una sola vez. Esto ata una
identidad a una clave de firma. Análogo al modelo *Passport* de RFC 9334.

> **Corrección al planteamiento inicial:** la firma única basta para *binding*,
> NO para *completitud*. Si el cliente no sigue co-firmando, la omisión de
> interacciones sueltas es indetectable. El enrollment habilita la co-firma
> continua de la Capa 2; no la sustituye.

### L2 — Co-firma continua + transparency log (mitiga B1 en el camino cofirmado)

- Cada interacción y **cada evento de inspección de contenido** se anexa a un log
  **append-only estilo RFC 9162** (se reutiliza y extiende el MerkleLogger
  existente, no se inventa uno nuevo).
- El cliente co-firma cada request con un **número de secuencia monótono**. Una
  laguna en los requests que el cliente emitió es detectable por ese cliente.
  Esto no demuestra que una inspección interna u otro efecto off-path no pueda
  omitirse antes de llegar al log.
- **Consistency proofs** permiten verificar que una historia observada sólo se
  extendió. Impedir una vista partida requiere un protocolo adicional de
  witnesses/monitores; no es una garantía suministrada por RFC 9162 ni por un
  witness que comparta proceso y dominio de privilegio con el log.
- L2 desdobla en **L2** (co-firma monótona + salting causal) y **L2b** (inspección de contenido bajo causa).

### L3 — Attestation + witnesses + evasion detection (diseño para mitigar B2)

- **L3a — Enclave.** El inspector corre en VM confidencial (TDX/SEV-SNP) y emite
  un quote firmado que ata la medición a un **build reproducible y publicado**.
  Verifiers = **usuario Y regulador** appraisan el quote contra la medición
  publicada (RFC 9334, Background-Check).
- **L3b — Witness quorum.** El diseño requiere witnesses independientes que
  validen consistencia y cosignen checkpoints; el usuario debe exigir quorum
  antes de confiar. Esta operación multi-actor no está desplegada.
- **L3c — Detección de evasión + behavioral drift.** Monitoreo continuo de cambios
  en las heurísticas de rechazo del modelo. Si la tasa de aceptación de cierta
  categoría desvía sin justificación operacional, escala a revisión (Decider). El
  log registra cada cambio de comportamiento, permitiendo análisis causal posterior
  y memoria inmune (ADR-049/054).

---

## Alcance honesto: qué se construye ahora y qué no

| Pieza | Estándar | Construible en solitario hoy | Plan |
|---|---|---|---|
| Log append-only + inclusion/consistency proofs | RFC 9162 | **Sí** (software puro, testeable) | **Build ahora** sobre MerkleLogger |
| Co-firma del cliente + secuencia monótona | — | **Sí** | **Build ahora** |
| Detector local de omisión + comparación de STH | RFC 9162 para proofs; protocolo de witness separado | **Sí** como prueba funcional in-process, **no** como neutralidad desplegada | **Build ahora**, sin reclamar cierre de split-view |
| Attestation real TDX/SEV-SNP | RFC 9334 | **No** (depende de hardware/cloud) | Interfaz `AttestationProvider` + impl software ahora; real diferido |
| Red de witnesses distribuida + quorum | C2SP `tlog-witness` / `tlog-cosignature` | **No** (varios actores) | Estructura + verify ahora; despliegue = ecosistema |

> No prometo un CT log de producción ni un enclave atestiguado en un autobuild de
> 3 iteraciones: sería deshonesto. Se construyó el núcleo criptográfico que
> prueba propiedades de los eventos observados; no prueba completitud off-path
> ni neutralidad. Lo dependiente de hardware/varios actores queda tras interfaz,
> con implementación software sólo para tests funcionales.

---

## Criterios de aceptación del núcleo (lo que validará el build)

1. Append-only verificable: dado un log L1 ⊆ L2, `verify_consistency(L1, L2)` pasa;
   ante reescritura de historia, falla.
2. Inclusión: `verify_inclusion(entry, STH)` pasa para entradas presentes, falla
   para ausentes.
3. **Detección acotada de omisión:** si falta un request que el cliente sí emitió,
   detecta la laguna en su secuencia. No cubre una inspección/efecto off-path.
4. **Comparación local de vista:** dos STH inconsistentes presentados al mismo
   verificador fallan. No demuestra gossip, quorum ni independencia desplegados.
5. `AttestationProvider` tras interfaz, con impl software que un test puede
   ejercitar; el inspector la consulta antes de operar.

## Consecuencias

- El eje de ADR-051 ("verifícalo, no confíes") tiene primitives verificables
  para eventos observados, pero su claim de completitud sigue provisional.
- Quedan abiertos (ecosistema, no código en solitario): operar witnesses reales,
  hardware confidential, certificación de terceros, modelo económico.

## Revalidación normativa — 2026-08-12

Esta sección corrige una atribución material de la versión aceptada; no declara
construida capacidad nueva.

**Disposición:** se conserva la decisión de construir estas capas. Su claim de
cierre end-to-end de B1/B2 queda contradicho y la evidencia se califica
`PROVISIONAL` hasta demostrar completitud off-path, independencia y quorum.

- **VERIFICADO:** [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html)
  define inclusion/consistency proofs, pero dice que un log puede mostrar vistas
  inconsistentes, que el remedio queda fuera de su alcance y que el gossip no se
  define allí (§1 y §11.3). Por tanto, las frases anteriores que atribuían a ese
  RFC una defensa completa por witnesses eran un sobreclaim.
- **VERIFICADO:** [C2SP `tlog-witness`](https://c2sp.org/tlog-witness@v1.0.0)
  especifica un witness con estado que valida una consistency proof antes de
  cosignar; [`tlog-cosignature`](https://c2sp.org/tlog-cosignature@v1.0.1)
  permite a clientes exigir quorum antes de confiar en una inclusión. La propia
  especificación de witness deja pendiente cómo impedir que los clientes queden
  particionados respecto de monitores.
- **VERIFICADO en el grafo fresco de Atlas:** existen
  `atlas.transparency.log`, `atlas.transparency.merkle_tree` y
  `atlas.transparency.client_cosign`; no apareció un módulo witness/SCITT. Este
  árbol tampoco tiene una arista directa al `atlas.logging.merkle_logger` usado
  ampliamente por el runtime.
- **NO VERIFICABLE:** independencia entre log, gateway, witness y claves;
  completitud de efectos fuera del camino instrumentado; quorum distribuido
  operativo. Los tests in-process siguen siendo evidencia de la función
  criptográfica, no de un operador neutral ni de protección frente a
  particiones desplegada.

Evidencia ampliada y consecuencias arquitectónicas:
`work/research/OVERSIGHT_TRANSPARENCY_MCP_VETTING_2026-08-12.md`.
