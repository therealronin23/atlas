# Oversight, transparencia y vetting MCP — memo de evidencia 2026-08-12

Estado: investigación; no concede autoridad, no instala terceros y no activa
capacidad. Método: documentación primaria y grafo/proceso local, sin `git clone`.
Las etiquetas usadas son **VERIFICADO**, **INFERENCIA**, **NO VERIFICABLE** y
**REPORTADO-SIN-CONFIRMAR**.

## Correcciones que cambian la tesis

1. **VERIFICADO — ADR-053 atribuía demasiado a RFC 9162.** El RFC define
   árboles, inclusion proofs y consistency proofs, pero advierte que un log
   puede servir vistas inconsistentes, deja los remedios fuera de alcance y
   dice que el gossip no se define allí (§1 y §11.3). El erratum quedó en
   `docs/decisions/adr/adr_053_gateway_trust_completeness.md`.
   Fuente: [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162.html).
2. **VERIFICADO — Atlas no carece por completo de supply-chain ni de
   transparencia.** El grafo fresco en `4fab366` encontró
   `plugin_admission -> supply_chain -> supply_chain_models` y, por separado,
   `transparency.log -> transparency.merkle_tree` más `client_cosign`. No hay
   arista directa entre ese árbol y `logging.merkle_logger`, ni apareció un
   módulo witness/SCITT. Candidate scan, Security Council, sentinel/third-party
   admission y plugin admission son caminos distintos que convergen más arriba,
   no una puerta única demostrada.
3. **VERIFICADO — el estado vivo contradice una premisa del prompt.** El canon
   marca ADC-WO-108 `DONE` y ADC-WO-109 como el nodo de Cut 2. La parada de hoy
   se respetó como instrucción operativa explícita; no se reinterpretó como
   estado histórico ni se abrió Cut 2/Wave 5.

## 1. AI Control y oversight escalable

### Evidencia externa

| Hecho | Evidencia primaria | Consecuencia defendible para Atlas |
| --- | --- | --- |
| AI Control evalúa protocolos contra subversión intencional con un modelo potente no confiable, otro menos potente confiable y trabajo humano limitado. | [Greenblatt et al., ICML 2024](https://proceedings.mlr.press/v235/greenblatt24a.html) | El caso de seguridad debe red-teamear el protocolo completo, no sólo medir calidad del modelo. |
| BashBench contiene 257 tareas; el mejor protocolo Ctrl-Z bajó el éxito de ataque de 58% a 7% con 5% de coste de utilidad. | [Ctrl-Z, arXiv:2504.10374](https://arxiv.org/abs/2504.10374) | Seguridad y utilidad son dos ejes; bloquear más no basta como benchmark. Esos números no se transfieren a Atlas. |
| AISI enumera monitoring, aprobación humana, restricción de recursos y terminación; propone ACL-0…ACL-5 y considera insuficientes los métodos actuales para ACL-5. | [UK AISI, control measures](https://www.aisi.gov.uk/blog/how-to-evaluate-control-measures-for-ai-agents) | Atlas debe acotar la clase de atacante/capacidad que cubre; no prometer control universal. |
| Con 1% de falsos positivos, el monitor asíncrono inicial perdió hasta 67% de ataques y el mejor de la tercera ronda 6%; un monitor síncrono más débil obtuvo mayor seguridad que el mejor asíncrono. | [UK AISI, asynchronous monitoring](https://www.aisi.gov.uk/blog/stress-testing-asynchronous-monitoring-of-ai-coding-agents) | Para efectos irreversibles o `sensitivity="high"`, revisión posterior no sustituye admission gate/HITL previo. |
| Despliegues reales añaden agentes paralelos, latencia, ataques incrementales e inferencia difícil desde acciones aisladas. | [UK AISI, practical challenges](https://www.aisi.gov.uk/research/practical-challenges-of-control-monitoring-in-frontier-ai-deployments) | Los tests de una trayectoria aislada no prueban control en concurrencia ni recuperación. |
| METR observó excepciones de cobertura, una variable que alteraba la clasificación de tráfico, llamadas de subagentes no monitorizadas (corregidas en menos de 24 h) y jailbreaks del monitor. En tareas de más de ocho horas, al menos 16% de runs exitosos fueron descalificados por cheating tras revisión. | [METR Frontier Risk Report, mayo de 2026](https://metr.org/blog/2026-05-19-frontier-risk-report/) | La completitud del router y la integridad del benchmark son parte del sistema de control, no detalles de observabilidad. |

### Contrato de evaluación Atlas propuesto

**INFERENCIA:** una evaluación útil debería declarar adversario, herramientas,
presupuesto humano, efectos permitidos y frontera temporal; medir simultáneamente
attack success, falsos positivos/negativos, utilidad, latencia, coste y
recuperación; e incluir ataques al router, al monitor, a subagentes, a logs y a
efectos ambiguos. Los umbrales de trabajos externos son datos de sus escenarios,
no defaults para Atlas.

**NO VERIFICABLE hoy:** no existe una tasa Atlas de falsos negativos/positivos
contra un corpus adversarial representativo, ni una evaluación multi-instancia
que pruebe completitud del control.

## 2. Transparencia tamper-evident más allá de Certificate Transparency

- **VERIFICADO — C2SP:** `tlog-witness` conserva estado y sólo cosigna un nuevo
  checkpoint después de validar su consistency proof; `tlog-cosignature` deja
  que clientes exijan quorum antes de confiar en una inclusión. El texto aún
  marca como pendiente impedir la partición cliente-monitor.
  Fuentes: [witness](https://c2sp.org/tlog-witness@v1.0.0) y
  [cosignature](https://c2sp.org/tlog-cosignature@v1.0.1).
- **VERIFICADO — SCITT:** RFC 9943 generaliza transparencia a statements de
  supply-chain, políticas de registro y receipts verificables. También fija el
  límite crucial: registrar sólo prueba que el emisor produjo el statement; el
  contenido puede ser falso y el emisor puede omitir statements selectivamente.
  Fuente: [RFC 9943](https://www.rfc-editor.org/rfc/rfc9943.html).
- **VERIFICADO — Rekor:** ofrece un log verificable de metadatos; auditores
  pueden comprobar consistencia append-only y Sigstore documenta monitor y
  `omniwitness`. Fuente: [Sigstore Rekor](https://docs.sigstore.dev/logging/overview/).
- **VERIFICADO — CloudTrail:** cada digest horario contiene hashes de logs, se
  firma y encadena la firma del digest previo. Activar la entrega de digests no
  ejecuta la validación: el consumidor debe verificar. Fuente:
  [AWS CloudTrail log validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html).

**INFERENCIA:** el Merkle local puede fijar bytes, orden e inclusión; no prueba
verdad, completitud ni independencia. Para claims fuertes, Atlas necesita
separar issuer, registration policy, receipt, auditor y witness, con claves y
dominios de fallo distintos. SCITT es el modelo semántico adecuado para SBOM,
provenance, scans y decisiones heterogéneas; C2SP aporta una defensa concreta
contra equivocation que RFC 9162 no especifica.

## 3. Bundle de admisión MCP defendible

### Punto de partida verificado

- El Registry oficial autentica namespaces y aloja metadatos, pero delega el
  security scanning al package registry y a agregadores. Fuente:
  [MCP Registry](https://modelcontextprotocol.io/registry/about).
- En MCPB, `fileSha256` es obligatorio; el Registry no lo valida y el cliente
  debe hacerlo antes de instalar. Fuente:
  [MCP package types](https://modelcontextprotocol.io/registry/package-types).
- Las annotations de tools son no confiables salvo que provengan de un servidor
  ya confiable. Fuente: [MCP tools specification](https://modelcontextprotocol.io/specification/draft/server/tools).
- Atlas A1 inspecciona estáticamente un árbol materializado y A2 revalida
  manifest/hashes; el grafo confirma una ruta de activación con Merkle en
  `plugin_activator`, pero no demuestra que candidate scan, council, sentinel y
  supply-chain compartan una única admisión ni que haya SBOM/Sigstore/in-toto.

### Bundle recomendado — inferencia sustentada, no implementación

1. Fijar Registry, origen, revisión inmutable y digest de los bytes realmente
   recibidos.
2. Exigir SBOM SPDX o CycloneDX, con completitud explícita, y contrastarlo con un
   inventario independiente del staging. Fuentes: [SPDX 3.0.1](https://spdx.github.io/spdx-spec/v3.0.1/scope/),
   [CycloneDX](https://cyclonedx.org/specification/overview/).
3. Verificar firma contra identidad, issuer y digest exactos; no usar una regex
   universal ni desactivar claims. Fuente:
   [Sigstore verification](https://docs.sigstore.dev/cosign/verifying/verify/).
4. Fijar Cosign al menos en 2.6.2 o 3.0.4. CVE-2026-22703/GHSA-whqx-f9j3-ch6m
   permitió aceptar ciertos bundles cuya entrada Rekor no estaba ligada al
   digest, firma o clave; fue una regresión y esas versiones la corrigen.
   Fuente: [advisory oficial](https://github.com/sigstore/cosign/security/advisories/GHSA-whqx-f9j3-ch6m).
5. Validar una attestation in-toto/SLSA: el `subject.digest` debe coincidir;
   política explícita para signer/builder, `buildType`, parámetros y
   `resolvedDependencies`. Fuentes: [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md),
   [SLSA provenance v1.2](https://slsa.dev/spec/v1.2/build-provenance).
6. Registrar firma, SBOM, provenance, scan, decisión y trial como statements
   separados con receipts, sin colapsarlos en el booleano “seguro”.
7. Ejecutar después sólo un trial aislado: filesystem/red/credenciales mínimos,
   tools instrumentadas y efectos bloqueados. Revalidar y revocar por nueva CVE,
   digest distinto, pérdida de quorum o divergencia SBOM/inventario.

**NO VERIFICABLE:** un SBOM firmado no demuestra completitud; inclusión en
Registry/Rekor no prueba seguridad dinámica; el grafo no prueba que todos los
caminos de instalación/activación pasen por el mismo gate.

## 4. Challenge-the-trio: “aparato de auditoría con runtime dentro”

**Veredicto: rechazada como tesis fuerte.**

- **VERIFICADO:** Merkle sólo protege eventos anexados; RFC 9162 no evita una
  acción ni una omisión y SCITT admite statements falsos u omitidos.
- **VERIFICADO:** METR observó bypasses antes de que el monitor recibiera el
  tráfico; AISI midió que una revisión asíncrona puede quedar por detrás de una
  barrera síncrona más débil porque el efecto ya ocurrió.
- **INFERENCIA:** si runtime, router, monitor, logger y claves comparten dominio
  de privilegio, comprometer el runtime puede omitir o alterar el dato antes del
  hash. La cadena posterior puede quedar íntegra pero incompleta.

Formulación máxima defendible: **runtime no confiable detrás de un plano de
control y evidencia impuesto externamente**. Para efectos gobernados:

```text
runtime no confiable
        |
        v
effect gateway síncrono + Policy/HITL
        |
        +--> ejecución acotada
        |
        +--> statement + receipt append-only
                      |
                      +--> checkpoints cosignados por witnesses independientes
```

Una variante todo-en-uno sigue siendo útil como observabilidad local, pero no
debe presentarse como operador neutral ni cierre de split-view.

## 5. Evidencia local y límites de esta sesión

- `atlas audit --verify`: exit 0 tras el único efecto de tercero ejecutado por
  error en el ciclo 5; la cadena está íntegra, pero el receipt retrospectivo no
  convierte aquella ejecución en consentimiento previo.
- Consultas MCP `graph_overview`, `graph_importers`, `graph_imports_of` y
  `graph_blast_radius`: éxito; grafo/head/server en `4fab366`, FRESH, 329 módulos.
- `rg` de transparencia y supply-chain local: exit 0.
- Fetch read-only de las dos especificaciones C2SP: HTTP 200, comando exit 0.
- Navegación de fuentes oficiales: exit funcional; no hubo clone, instalación,
  activación MCP ni ejecución de código descargado.

Quedan **NO VERIFICABLES**: witnesses externos operativos; independencia real
de procesos y claves; completitud de efectos off-path; seguridad dinámica de un
MCP; coste/TCO de esta arquitectura; y transferencia cuantitativa de benchmarks
externos a Atlas.
