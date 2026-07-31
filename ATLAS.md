# Atlas Definitive Candidate

Estado: **candidata para aprobación del operador**, compilada sobre
`c95038c9d7e97ddc6339f38abe6dad09b166f47d` el 2026-07-27.

Solo el operador puede elevar esta candidata a **ATLAS CANON ACCEPTED**.

## Qué es Atlas

Atlas es un sistema operativo cognitivo soberano, local-first y distribuido.
Coordina modelos, agentes, herramientas, MCP, memoria, conocimiento,
planificación, ejecución, aprobación humana, evidencia, recuperación,
autoconstrucción y superficies de producto bajo una autoridad explícita.

No es un chatbot con herramientas, un wrapper de APIs, un SaaS convencional,
una interfaz sin núcleo ni una copia de otro agente o framework. Su estrategia
permanente es **selective assimilation without cloning**: observar, medir y
adoptar capacidades externas útiles dentro de los invariantes de Atlas, sin
heredar su autoridad ni su diseño completo.

## Límites no negociables

1. Todo efecto externo deja evidencia auditable.
2. El código generado pasa AST Guard antes de ejecutarse.
3. Los agentes no modifican `config/governance.json`.
4. La sensibilidad alta exige control humano o denegación.
5. Un modo térmico degradado no carga modelos pesados.
6. Toda dependencia nueva necesita una decisión aceptada.
7. Todo cambio de código necesita pruebas relevantes.
8. Una adopción externa es no confiable hasta demostrar lo contrario.
9. La ejecución de terceros es reversible y fail-closed.
10. Una copia documental no es corroboración independiente.
11. `LIVE_VERIFIED` exige una observación fresca, fechada y satisfactoria.
12. La auto-adopción de MCP ejecutables remotos sigue rechazada.
13. Native Wave 5 sigue condicionada y bloqueada.
14. Golden Route conserva aprobación antes de efectos.
15. El grafo estructural fresco manda sobre la estructura actual.
16. GraphRAG semántico propone hipótesis, no hechos automáticos.
17. La memoria privada se destila antes de entrar en grafos compartibles.
18. Las superficies canónicas tracked tienen cobertura de CI.

Los contratos ejecutables y sus autoridades están en
[`docs/canon/contract_registry.jsonl`](docs/canon/contract_registry.jsonl).

## Arquitectura en una página

```text
Prime / apps dedicadas / superficies de producto
                 │ proyecciones, intención, aprobación
                 ▼
Trunk + Context ── Cognition Runtime ── Memory + Knowledge
                 │ planes y decisiones
                 ▼
Policy + Security + Gates + Runtime + Recovery
                 │ efectos permitidos y recibos
                 ▼
Integraciones / MCP / Hermes / nodos / Hosted

Evidence + Merkle + Reality cruzan todas las capas.
Foundry construye candidatos aislados; nunca se promociona a sí mismo.
Membrane/Osmosis audita bilateralmente; investigación no equivale a enforcement.
```

La descripción completa separa
[`CURRENT`, `TARGET` y `TRANSITION`](ARCHITECTURE.md). Ninguna flecha del
diagrama concede autoridad: las autoridades y contratos son explícitos.

## Autoridad

La constitución sigue distribuida conforme a ADR-067. Este fichero es la
**entrada humana única**, no una quinta constitución. El registro
[`docs/canon/authority_registry.yaml`](docs/canon/authority_registry.yaml) es
la entrada máquina única y enlaza las fuentes que mandan en cada alcance.

Para saber **qué existe hoy**:

1. runtime fresco;
2. código;
3. tests;
4. configuración;
5. estado vivo;
6. historia.

Para saber **qué debe ser Atlas**:

1. directiva actual del operador;
2. decisiones explícitas del operador;
3. invariantes constitucionales;
4. ADR aceptados y no supersedidos;
5. canon reconciliado del paquete;
6. diseños, propuestas e investigación, en ese orden.

Cuando dos fuentes válidas no pueden reconciliarse por alcance o supersesión,
el conflicto permanece visible y se eleva; la recencia o la repetición no lo
resuelven.

## Programas permanentes

Atlas mantiene trece programas, no fases desechables:

| Programa | Misión permanente |
|---|---|
| P00 | Canon and Governance |
| P01 | Institutional Kernel |
| P02 | Trunk and Context Control |
| P03 | Cognition Runtime |
| P04 | Memory and Continuity |
| P05 | Knowledge and Research |
| P06 | Self-Build and Foundry |
| P07 | Integration and Protocols |
| P08 | Product OS and UI/UX |
| P09 | Security, Evaluation, Operations and Recovery |
| P10 | Hermes and Distributed Atlas |
| P11 | Hosted and Native Substrate |
| P12 | Membrane, Osmosis and Bilateral Audit |

Sus contratos, gates, riesgos y criterios de finalización viven en
[`PROGRAMS.md`](PROGRAMS.md). Las olas ordenan entregas; nunca sustituyen estos
programas.

## Estado honesto

La base contiene un núcleo Python amplio y probado, Reality/Merkle operativos,
Mission/Golden Route v0, memoria, conocimiento, Foundry, integraciones y
mecanismos de seguridad reales. El grafo estructural fue fresco para el
baseline y queda stale tras los cambios de la candidata hasta su siguiente
rebuild. Nada de ello convierte automáticamente una pieza en producto
aceptado.

Límites actuales que deben permanecer visibles:

- `atlas-shell` es un **VALIDATION_HARNESS**, no la UX final;
- LivingGraph vive dentro de ese arnés;
- Universal Bar usa un pipeline simulado v1;
- Presence Engine y Liquid UI son diseño objetivo;
- ADR-078 acepta Atlas Engineering Workbench como primer producto y la línea
  CodeOSS/VSCodium como host de escritorio, pero ambos siguen en
  **ACCEPTED_DESIGN**, no `PRODUCT_ACCEPTED`;
- Void conserva código precursor como donante de capacidades, y Zed como
  donante ACP/de patrones; ninguno sustituye Atlas Core ni está wired en esta
  candidata;
- la proyección Android exigida por ADR-071 sigue sin implementación y se
  construirá sobre contratos estables, no presentando desktop como móvil;
- Hermes conserva código e historia, pero no quedó `LIVE_VERIFIED` en el
  preflight fresco;
- MCP configurado no significa conexión viva;
- ADR-076 A/B son opt-in; C está rechazado y no implementado;
- ADR-077 A/B/D tienen implementación parcial y el proceso observado tenía el
  flag configurado; C (escalado universal a `Task.AWAITING_APPROVAL`) falta y
  no hay evidencia fresca de tráfico exitoso;
- el bridge 7341 tiene una **excepción acotada aceptada** (ADR-080,
  2026-07-31): la superficie de producto de Fase 15 (Fabric, onboarding,
  Business Core) es mutante por diseño, mientras las rutas del núcleo siguen
  read-only según ADR-058/071. `business/core/activate|reject` escriben
  receipt Merkle verificable (`ADC-WO-107` DONE);
- Hosted Linux es el sustrato actual; Native Wave 5 sigue bloqueada;
- Membrane/Osmosis permanece como programa propio, con una sola promoción
  acotada mediante ADR-074.

El detalle verificable está en [`STATUS.md`](STATUS.md) y en la
[`matriz máquina`](docs/canon/component_reality_matrix.jsonl).

## Cómo continuar

1. Lee esta entrada.
2. Consulta [`STATUS.md`](STATUS.md) para no confundir objetivo con realidad.
3. Consulta [`ARCHITECTURE.md`](ARCHITECTURE.md) y el programa afectado en
   [`PROGRAMS.md`](PROGRAMS.md).
4. Elige un work order `READY` en
   [`docs/canon/implementation_registry.yaml`](docs/canon/implementation_registry.yaml).
5. Verifica decisión, grafo/blast radius, tests, rollback y autoridad humana.
6. Implementa en aislamiento, valida y deja recibos.
7. Ejecuta `python scripts/check_canon.py` antes de integrar.

Las decisiones todavía reservadas al operador y el orden de transición están
en [`PLAN.md`](PLAN.md). La trazabilidad completa parte de
[`docs/canon/authority_registry.yaml`](docs/canon/authority_registry.yaml).
