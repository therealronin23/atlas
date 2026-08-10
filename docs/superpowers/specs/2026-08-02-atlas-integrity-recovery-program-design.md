# Programa de recuperación de integridad de Atlas

- **Estado:** aprobado por el operador; ejecución autorizada y en curso
- **Fecha:** 2026-08-02
- **Baseline inspeccionado:** `813d0b8e7a34b94600840231c4ef4a873fbe9bec`
- **Ámbito:** runtime, canon de decisiones, fronteras de confianza, realidad/CI y reconciliación del producto UI
- **No modifica:** `config/governance.json`

## 1. Resultado

Atlas detiene la construcción sobre afirmaciones no demostradas y recupera una
base operativa y decisional verificable antes de continuar T2.1.

El operador declaró literalmente el 2026-08-02: «No, fue una sugerencia que yo
acepte sin pensarlo mucho». De esa declaración inferimos que ADR-082 no demuestra
una elección informada; no inferimos qué prototipos vio, probó o comparó. Por
tanto:

1. Flutter deja de ser una decisión canónica válida.
2. Ningún stack alternativo pasa a ser ganador por descarte.
3. El alcance afectado de T2.1 queda sin resolver hasta reconciliar ADR-082 con
   ADR-071/ADR-078 y confirmar qué decisiones previas fueron realmente
   informadas. No se reabre ni se preserva automáticamente todo T2.1.
4. F2.6 permanece pendiente, pero no se ejecuta contra un canon que sabemos
   incorrecto. Por defecto se ofrecerá una corrida final después del último ADR
   del programa; una corrida intermedia también exige autorización específica.
5. Los defectos de runtime, autoridad y verificación encontrados durante la
   auditoría se corrigen antes de apoyar producto nuevo sobre ellos.

Este documento define el programa y los límites entre cortes. Cada corte tendrá
su propia especificación de implementación, plan, pruebas y commits.

## 2. Evidencia y nivel de confianza

### 2.1 Hechos vivos confirmados

En el baseline indicado:

- `atlas reality --json` informa `status=degraded`.
- `atlas-core.service` está inactivo. Se detuvo deliberadamente después de
  observar un bucle de reinicios causado por una colisión de puerto.
- el puerto `127.0.0.1:9091` pertenece al Prometheus Pushgateway del sistema;
  Atlas intenta enlazar su exporter en el mismo puerto cuando
  `ATLAS_PROMETHEUS=1`;
- el grafo estructural estaba `FRESH` y coincidía con ese baseline. El commit
  documental de esta especificación avanzó después el HEAD, por lo que debe
  regenerarse antes de calcular blast radius de implementación;
- ColdUpdate conserva una validación histórica fallida;
- F2.6 está `due` por la incorporación de ADR-082;
- el árbol de trabajo ya contenía cambios ajenos a este programa en
  `.gitignore` y `docs/fixtures/`; deben conservarse y permanecer fuera de sus
  commits.

### 2.2 Defectos reproducidos en código

La auditoría reprodujo cuatro problemas de fundamento:

1. `ServiceRunner.start()` propaga el error de bind de un exporter opcional.
   Como systemd usa `Restart=always`, una colisión estable produce un restart
   storm.
2. El lifecycle no es transaccional: si el arranque falla antes de marcar
   `_started=True`, `stop()` no limpia los componentes iniciados parcialmente.
3. `_copy_defaults()` puede sustituir el `governance.json` del workspace desde
   una raíz seleccionada por entorno antes de inicializar la auditoría Merkle.
4. `_sync_permissions_file()` solo acumula permisos. Una autorización eliminada
   del baseline no se revoca; además sincroniza campos que `PermissionProfile`
   ignora porque sus valores efectivos están hardcodeados. Un YAML corrupto se
   transforma silenciosamente en un perfil vacío con comportamiento parcial de
   respaldo.

También se reprodujo que `atlas reality --strict` puede devolver verde con
grafo obsoleto, ColdUpdate degradado, F2.6 pendiente o providers históricos
muertos. No todos esos estados deben bloquear todos los perfiles, pero ninguno
debe desaparecer de la semántica del gate.

Las reproducciones de permisos, gobernanza y `reality` se hicieron en
directorios temporales o con reportes sintéticos y todavía no son fixtures
versionados. El primer test rojo de cada subcorte debe conservar la
reproducción antes de cambiar producción.

### 2.3 Evidencia histórica contradictoria

ADR-082 atribuye a Flutter aproximadamente 42–58 MB de RAM y menos de 250 ms de
arranque. Los informes existentes del repositorio registran, para sus micro-PoC
Linux, cifras distintas:

- Flutter: aproximadamente 186 MB y 1,5 s;
- Compose: aproximadamente 282 MB y 8,1 s;
- Qt6/QML: aproximadamente 134 MB y 1,2 s.

El mismo corpus indica que Qt obtuvo las mejores cifras Linux de esos
micro-PoC, que el Cónclave anterior consideró insuficiente una sola pantalla
para extrapolar a unas veinte, y que Android quedó fuera de aquella medición.

Estos informes sirven para probar la contradicción documental, no como verdad
final de producto. Sus comandos, builds y resultados deberán reproducirse bajo
un harness común antes de una nueva decisión.

### 2.4 Matriz de trazabilidad inicial

| Claim | Fuente inspeccionada | Reproducción/observación | Clase |
| --- | --- | --- | --- |
| restart storm por `9091` | `service_runner.py`, `prometheus_exporter.py`, unidad systemd | `systemctl show`, `ss`, readiness de Pushgateway y journal; 4.781 reinicios acumulados | viva, 2026-08-02 |
| sync monotónica de permisos | `orchestrator.py::_sync_permissions_file` | fixture temporal: una entrada retirada del source permaneció en destination | reproducción local pendiente de convertir en test P1 |
| overwrite de gobernanza | `orchestrator.py::_copy_defaults`, `runtime_paths.py` | fixture temporal con `ATLAS_CORE_ROOT` alternativo sustituyó el snapshot | reproducción local pendiente de convertir en test G1 |
| falso verde estricto | `reality.py::_overall_status/strict_failures` | reporte sintético con grafo stale, ColdUpdate degradado y F2.6 due produjo `ok`/sin fallos | reproducción local pendiente de convertir en test V1 |
| ADR-082 no fue elección informada | conversación del operador | «No, fue una sugerencia que yo acepte sin pensarlo mucho» | declaración directa, 2026-08-02 |
| métricas UI incompatibles con ADR-082 | informes Flutter/Compose/Qt del repositorio | valores resumidos en §2.3; reproducción común aún pendiente | historia local, no veredicto final |

## 3. Principios vinculantes

1. **Contención antes que expansión.** No se añade producto sobre un runtime en
   restart storm o una autoridad de configuración ambigua.
2. **Historia preservada, canon corregido.** Los registros erróneos no se borran
   ni se maquillan; se superseden con motivo y evidencia trazable.
3. **Una autoridad por dato.** Baseline de seguridad, personalizaciones del
   operador y estado derivado no se mezclan en un mismo fichero sin procedencia.
4. **Fail-closed para efectos.** Un error de configuración de permisos nunca
   habilita escrituras, shell, red o acciones externas por fallback.
5. **Degradación explícita para componentes opcionales.** Un exporter opcional
   puede fallar sin derribar Atlas, pero el fallo debe ser visible y auditable.
6. **Un gate declara su perfil.** Desarrollo, runtime, release y sucesión no
   comparten ciegamente los mismos bloqueadores.
7. **Medir el caso real.** Un micro-PoC de una pantalla no decide una aplicación
   multi-superficie ni demuestra Android.
8. **El operador elige preferencias, no valida cifras de memoria.** Atlas
   reproduce y compara la evidencia técnica; el operador decide requisitos y
   carácter de producto después de probar resultados reales.
9. **Cambios pequeños y reversibles.** Cada corte se integra y verifica antes
   del siguiente.
10. **Sin bypass de gates.** Que una herramienta figure como “verificada” no
    autoriza saltarse Sentinel si su artefacto real no supera la admisión.

## 4. Arquitectura del programa

```text
Contención
   +--> C1. Reparación del canon inicial -------------------------------+
   |
   +--> R1. Exporter/estado --> R2. Lifecycle --> R3. systemd ----------+
                                                                      |
       G1. Bootstrap de gobernanza ------------------------------------+
                                                                      |
       P1. Schema/migración --> P2. Evaluación --> P3a/b/c. Gate/efectos +
                                                                      |
                                                                      v
                                                  A. Activación controlada
                                                                      |
                                                                      v
                                                  V. Realidad y CI honestos
                                                                      |
                           C1 + V --> U0. Reconciliar producto/plataformas
                                         |
                                         +--> U1/U2/U3 solo si hacen falta
                                                        |
                                                        v
                                             último ADR/disposición
                                                        |
                                                        v
                                             F2.6 final autorizado
```

R y C pueden prepararse en paralelo. Reparar R no autoriza por sí solo a
reactivar el servicio autónomo: A depende también de G1 y P3c. El primer smoke de
A deshabilita schedulers y efectos; la autonomía se recupera después de probar
el gate de confianza. V se apoya en esos contratos para describir el runtime
real. U es condicional y no empieza a construir una aplicación definitiva:
primero reconcilia el producto y solo después produce la evidencia que siga
faltando.

## 5. Corte R — recuperación operativa del runtime

R se divide en R0 (contención ya aplicada), R1 (exporter y estado), R2
(lifecycle) y R3 (unidad/readiness). `atlas-core.service` permanece detenido
durante R; los smokes usan procesos aislados con autonomía y schedulers
deshabilitados.

### 5.1 Contrato de configuración

- `ATLAS_PROMETHEUS_MODE=off|optional|required` define la semántica. Durante la
  migración, `ATLAS_PROMETHEUS=true` equivale a `optional` y falso/ausente a
  `off`; valores contradictorios fallan con diagnóstico.
- host y puerto se parsean mediante funciones validadas; un valor inválido no
  genera un traceback sin contexto.
- el exporter se considera opcional salvo que exista un modo explícito
  `required`. El modo opcional contiene `EADDRINUSE` y otros fallos de arranque,
  registra estado degradado y permite continuar el servicio.
- el host por defecto permanece en loopback. Exponer métricas fuera de loopback
  requiere una decisión de seguridad explícita.
- `9464` será el default dedicado del exporter, tras comprobar que no colisiona
  con los puertos Atlas o Prometheus ya reservados. Un override continúa siendo
  posible y siempre se valida.
- Atlas no edita `.env` ni el scraper silenciosamente. La migración del
  workspace produce dry-run y diff; el operador aprueba cualquier cambio local.

### 5.2 Contrato de estado y readiness

`ServiceRunner` mantendrá un registro tipado de componentes y publicará una
proyección atómica `runtime/service_status.json`, modo `0600`, que contiene:

- versión de schema, versión Atlas e `instance_id` aleatorio por boot;
- PID y tiempo de inicio del proceso;
- estado `starting | ready | degraded | failed | stopped`;
- componentes obligatorios/opcionales con razón y timestamp;
- endpoints habilitados y su mismo `instance_id`.

La proyección no sustituye a Merkle: cada transición se audita primero y el
fichero es estado derivado para readiness y `atlas reality`. Se escribe mediante
temporal en el mismo directorio, `fsync` y rename. El instalador verifica que el
PID coincide con `MainPID` de systemd y que los endpoints obligatorios devuelven
el `instance_id` vigente. Prometheus expone además una métrica de identidad de
runtime; `atlas_up 1` por sí sola no demuestra propiedad del listener.

### 5.3 Lifecycle transaccional

`ServiceRunner.start()` mantendrá un registro ordenado de componentes adquiridos.
Ante cualquier excepción fatal:

1. registra `service.start_failed` con el componente y error sanitizado;
2. revierte en orden inverso solo los componentes realmente iniciados;
3. deja `_running=False` y un estado coherente aunque `_started` nunca llegara a
   ser verdadero;
4. vuelve a elevar el fallo cuando el componente sea obligatorio;
5. conserva el servicio si el único fallo pertenece a un componente opcional.

`stop()` será idempotente y limpiará estado parcial. No dependerá de una única
bandera que solo se activa al final del arranque. La pila de rollback incluirá
threads, schedulers, servidores, monitores y suscripciones. Si EventBus no puede
desuscribir, R2 añadirá ese contrato o hará el wiring estrictamente único por
vida del proceso. Un fallo de un `stop()` no impide intentar los restantes.

### 5.4 systemd y activación

- la unidad limitará ráfagas de reinicio para que un fallo persistente no genere
  miles de procesos y trazas;
- readiness verificará el proceso y cada endpoint obligatorio habilitado;
- un endpoint ajeno que responda en el puerto esperado no contará como Atlas;
- el instalador distinguirá `active` transitorio de readiness estable;
- las pruebas de unidad usarán un `systemctl` falso. El smoke vivo será opt-in,
  operará solo sobre `atlas-core.service` y verificará también rollback de la
  unidad instalada;
- el gate A arranca primero con schedulers, proveedores y efectos externos
  deshabilitados. Solo después de G1/P3 y un smoke limpio puede restaurar la
  configuración autónoma previa.

### 5.5 Aceptación de R

- prueba de colisión real con un socket temporal ya ocupado;
- prueba de puerto inválido;
- prueba de exporter sano con `atlas_up 1` e identidad ligada a la instancia;
- prueba de rollback tras fallo en cada etapa relevante del arranque;
- doble `start()`, `stop()` repetido y fallos durante rollback no dejan threads,
  suscripciones ni componentes propios vivos;
- smoke de systemd demuestra contador de reinicios estable y readiness de
  Atlas;
- R termina con el código recuperado, pero el servicio sigue apagado hasta que
  A confirme también G1 y P3.

## 6. Corte C — reparación del canon de decisiones

### 6.1 Disposición de ADR-082

ADR-082 no se elimina. Se preserva como evidencia de una decisión inválidamente
cerrada y recibe una anotación mínima de supersesión. Un ADR posterior:

- declara que no existe stack ganador;
- registra la confirmación del operador sin reinterpretarla como preferencia de
  stack;
- enumera las contradicciones de evidencia;
- reconcilia su alcance con ADR-071 y ADR-078 sin confiar solo en que esos
  documentos digan “aceptado”;
- no reabre automáticamente T2.1/T2.2/T2.3 ni descarta automáticamente la
  elección CodeOSS/VSCodium de desktop;
- deja como pregunta explícita si Mission Console es una superficie del
  Workbench, una proyección Android o un producto adicional;
- define qué evidencia faltaría según la topología que el operador confirme;
- no convierte Qt en ganador por tener mejores cifras en el micro-PoC Linux.

El backlog, `decision_registry`, índice de ADR, `implementation_registry`,
matriz de realidad y cualquier estado derivado se actualizan en la misma unidad
lógica mediante estados y relaciones estructurados. Actualmente ADR-082 ni
siquiera figura en `decision_registry`; esa omisión no se perpetúa. No se
reescribe el pasado para fingir que ADR-082 nunca existió.

Como C materializa una petición humana sobre documentos canónicos, utiliza
Golden Route y ColdUpdate. Si esa ruta vuelve a fallar, el cambio no se aplica
por edición silenciosa: C queda bloqueado y se repara primero la ruta. Una vía
manual futura requeriría su propio contrato gobernado; este diseño no la crea ni
la autoriza.

### 6.2 F2.6

F2.6 sigue siendo una sesión LLM real y costosa. El programa no la ejecuta
silenciosamente ni altera su ledger para volverla `current`.

Después de integrar la supersesión, C:

1. se vuelve a consultar `atlas f26 status --json`;
2. se presenta al operador la notificación exacta vigente;
3. no consume por defecto una corrida que quedaría obsoleta al crear el ADR
   final de U;
4. permite una corrida intermedia solo con autorización específica;
5. difiere la corrida requerida para cerrar el programa hasta después del
   último ADR o disposición canónica producida por U;
6. un fallo abre trabajo correctivo y exige repetir la rúbrica completa.

Se exponen dos estados distintos: `engineering_complete` no implica
`operator_gate_complete`. La imposibilidad o falta de autorización para F2.6 se
declara como gate humano pendiente, no como éxito técnico ni como fallo
silenciado.

### 6.3 Aceptación de C

- ninguna fuente canónica afirma que Flutter sea definitivo;
- las relaciones de ADR-082 incluyen estado, supersesor y alcance afectado;
- T2.1, T2.2 y T2.3 no heredan un stack no elegido ni pierden decisiones
  independientes sin revisión;
- las cifras históricas se etiquetan por procedencia y alcance;
- la supuesta elección de CodeOSS desktop y el requisito Android quedan
  pendientes de confirmación factual del operador, no de lectura documental;
- sanitation e índices encuentran la nueva disposición;
- búsquedas de claims antiguos no encuentran una aceptación vigente sin enlace
  a su supersesión.

## 7. Corte T — fronteras de confianza

T se implementa como G1 (gobernanza) y P1/P2/P3 (permisos y cierre de efectos).
No se agrupan en un único diff.

### 7.1 G1 — raíz de confianza de gobernanza

Se separan tres conceptos hoy confundidos:

- **baseline constitucional package-owned:** recurso distribuido en el mismo
  dominio de confianza que el código Python realmente importado;
- **snapshot runtime:** copia verificable usada por el workspace;
- **migración:** operación explícita y auditada entre versiones.

En checkout editable, el baseline se resuelve desde la raíz validada que
contiene el módulo `atlas` ejecutado. En wheel, se distribuye como recurso del
paquete y se resuelve con APIs de recursos, no mediante `ATLAS_CORE_ROOT` ni un
`data-file` ambiental. Esto no aporta firma criptográfica de supply chain: el
trust anchor es la instalación de código elegida por el operador. Sí impide que
una raíz de datos sustituya solo la política.

El snapshot tendrá una máquina de estados:

- `ABSENT`: primer bootstrap permitido desde el recurso package-owned;
- `CURRENT`: versión y digest coinciden;
- `DIVERGED`: bytes distintos de una versión conocida;
- `INVALID`: schema, propietario, modo o topología de filesystem inseguros.

Reglas:

1. `ATLAS_CORE_ROOT`, `ATLAS_HOME` y otras rutas de datos nunca seleccionan el
   baseline constitucional.
2. Antes de migrar se verifica la cadena Merkle existente; si no existe, se crea
   su genesis antes del primer efecto gobernado.
3. `DIVERGED` o `INVALID` bloquean acciones gobernadas y ofrecen dry-run; nunca
   provocan overwrite automático.
4. Directorio, source, destination y backup se inspeccionan con `lstat` y
   política no-follow, dueño y modo. La escritura usa temporal en el mismo
   directorio, `fsync` y rename atómico.
5. El receipt incluye versión/digest anterior y nuevo, fuente package-owned y
   resultado de validación.
6. Este corte no cambia el contenido normativo de `config/governance.json`.

### 7.2 P1 — schema y migración de permisos

El schema v2 separa:

- baseline package-owned: zonas, allows grantables y revocaciones obligatorias;
- overlay local `0600`: grants, denies, `read_extended` y configuración Telegram;
- hard blocks constitucionales: no configurables por overlay;
- estado derivado: versión, procedencia y salud; nunca editado como autoridad.

Telegram IDs, `passphrase_hash`, rutas extendidas y cualquier valor semejante
son exclusivamente locales, se redactan en reportes y nunca se copian al
baseline. Claves desconocidas invalidan o ponen en cuarentena la sección; no se
ignoran silenciosamente.

El YAML heredado no permite distinguir de forma general un grant humano de un
residuo de una allowlist antigua. La migración:

1. hace backup `0600`, hash y dry-run;
2. clasifica por matriz de autoridad los campos inequívocos;
3. compara contra baselines históricos solo cuando su digest/versión sea
   demostrable;
4. marca entradas restantes como `legacy_unknown` y las deja denegadas;
5. solicita al operador clasificar cada `legacy_unknown` antes de promoverlo a
   grant;
6. escribe atómicamente y puede restaurar el original completo.

Nunca convierte automáticamente una entrada ambigua en autorización.

### 7.3 P2 — evaluación y precedencia

La precedencia efectiva es:

```text
hard blocks constitucionales
  > revocaciones obligatorias versionadas
  > denies locales
  > grants locales validados y dentro del ámbito grantable
  > allows del baseline
  > deny por defecto
```

Un grant local sobrevive a actualizaciones ordinarias, pero nunca vence un hard
block ni una revocación de seguridad. Cada decisión efectiva expone fuente,
versión y regla de precedencia. `absolute_blocks` y `system_read_allowed` tienen
una sola autoridad real; no quedan campos decorativos que el runtime ignore.

### 7.4 P3 — gate central e inventario de efectos

`PermissionProfile` no gobierna hoy todos los efectos: por ejemplo,
`CapabilityIssuer.issue_network()` depende de SSRFBridge y existen transportes
directos. P3 se divide para que cada cambio sea revisable y TDD:

- **P3a — gate central:** introduce salud
  `VALID | ABSENT | INVALID | UNMIGRATED`; `CapabilityIssuer` la aplica también
  a red y Orchestrator/Decider la comprueban antes de caminos mutantes o
  externos.
- **P3b — inventario ejecutable:** `config/effect_paths.json` registra cada
  familia/call site público, gate dueño, estado `migrated | blocked | pending`
  y tests. Un check CI compara el registro con el código para que un efecto
  nuevo o directo no aparezca sin clasificación.
- **P3c-n — cierre por familia:** filesystem/shell, red/providers,
  MCP/transportes y mensajería externa se migran o bloquean en commits
  separados. Ninguna familia `pending` puede llegar a A.

Solo el diagnóstico local read-only definido por el baseline inmutable sigue
disponible durante recuperación.

### 7.5 Aceptación de T

- checkout editable y wheel instalado resuelven su propio baseline;
- un `ATLAS_CORE_ROOT` adversarial no altera gobernanza;
- recurso ausente, baseline manipulado, symlink y migración interrumpida
  producen estado seguro y evidencia, no overwrite;
- retirar un allow ordinario lo elimina; una revocación obligatoria vence un
  grant; un deny local vence ambos allows;
- un grant local explícito y válido sobrevive a una actualización ordinaria;
- `legacy_unknown` permanece denegado hasta decisión humana;
- YAML corrupto niega escritura, shell, red y al menos un transporte que antes
  era directo;
- el inventario ejecutable no contiene familias `pending` antes de A y falla si
  aparece un call site externo sin registrar;
- cada decisión efectiva indica baseline/grant/deny/revocación y versión;
- los tests conservan las protecciones de symlink, rutas absolutas, Git
  read-only y cadenas shell.

### 7.6 A — activación controlada

A requiere R3, G1 y todas las familias P3c en `migrated` o `blocked`, además de
Merkle válido. No modifica `.env` sin diff aprobado. Genera un drop-in temporal
de systemd que fuerza:

- `ATLAS_DECIDER=human`;
- `ATLAS_DISABLE_TELEGRAM=1`;
- `ATLAS_MAINTENANCE_SCHEDULER=0`;
- `ATLAS_SELF_AUDIT_SCHEDULER=0`;
- `ATLAS_SWARM_SCHEDULER=0`;
- `ATLAS_AUDIT_SAMPLE_SCHEDULER=0`;
- `ATLAS_KNOWLEDGE_SCHEDULER=0`;
- `ATLAS_SERVE_DASHBOARD=0`;
- `ATLAS_PROMETHEUS_MODE=optional`, host loopback y puerto `9464`.

El gate ejecuta:

1. arranque foreground hermético de 60 segundos y shutdown limpio;
2. arranque systemd con el perfil seguro durante cinco minutos, tres lecturas de
   readiness y `NRestarts` sin incremento;
3. verificación Merkle y ausencia de receipts de red, MCP mutante, providers o
   mensajería durante la ventana;
4. restauración incremental de cada familia previamente habilitada, una por
   vez, con smoke específico y ventana equivalente;
5. rollback inmediato al perfil seguro si readiness cae, el contador aumenta o
   aparece un efecto no esperado.

Las ventanas se monitorizan de forma no bloqueante; no requieren mantener una
sesión de agente esperando. A termina cuando el servicio está listo con la
configuración aprobada o cuando queda estable en perfil seguro con las familias
fallidas explícitamente deshabilitadas.

## 8. Corte V — realidad y CI honestos

### 8.1 Modelo de severidad

Cada señal de `atlas reality` tendrá:

- frescura (`live`, `config`, `history`, `unknown`);
- severidad (`info`, `warning`, `blocking`);
- perfiles a los que bloquea;
- razón y acción siguiente.

Perfiles iniciales:

- `runtime`: integridad de gobernanza/Merkle, permisos cargados, daemon y
  endpoints obligatorios;
- `development`: tests seleccionados, tipos, grafo de código fresco y árbol
  inspeccionable;
- `release`: paridad CI, auditoría de dependencias, build/install smoke y gates
  canónicos;
- `succession`: canon e índices frescos y F2.6 vigente;
- `autonomy`: runtime, trust boundaries, scheduler y ColdUpdate aptos para
  operar sin supervisión continua;
- `legacy-strict`: compatibilidad temporal con las reglas previas de daemon,
  browser, docs, Merkle, security y checks ejecutados; se retira tras un ciclo
  de deprecación documentado.

Matriz normativa inicial (`B` bloquea, `W` advierte, `—` no aplica y `C`
bloquea solo si la capacidad se declaró requerida):

| Señal | runtime | development | release | succession | autonomy |
| --- | --- | --- | --- | --- | --- |
| gobernanza `!= CURRENT` | B | W | B | B | B |
| permisos `!= VALID` | B | W | B | B | B |
| Merkle corrupto | B | W | B | B | B |
| daemon inactivo | B | — | — | — | B |
| endpoint obligatorio caído | B | — | — | — | B |
| tests o tipos fallan | — | B | B | W | W |
| grafo de código stale | W | B | B | B | W |
| ColdUpdate degradado | W | W | W | W | B |
| F2.6 `due` | W | W | W | B | W |
| canon/índices stale | W | W | B | B | W |
| browser/provider no disponible | C | C | C | C | C |

`config/capability_requirements.json` declara por perfil qué browser, provider
o endpoint convierte una celda `C` en bloqueo; `--require-capability` puede
añadir requisitos para una ejecución concreta, nunca quitarlos. `unknown`
bloquea cuando la señal es obligatoria para el perfil solicitado y se pidió
evidencia viva; en los demás casos produce `W`, nunca `ok` implícito. Cada dato
histórico incluye timestamp y edad máxima. Los providers opcionales muertos no
bloquean indiscriminadamente.

La nueva semántica es un cambio versionado, no silencioso: `reality.v2` añade
`schema_version`, `signals`, `status_by_profile` y `failures_by_profile`.
`atlas reality --strict` sin `--profile` seleccionará `runtime`; la guía de
migración documentará el cambio respecto al gate anterior. Quien necesite la
semántica exacta previa puede usar `--profile legacy-strict` durante un ciclo de
deprecación. `status` y `strict_failures` permanecen como proyección del perfil
seleccionado para consumidores JSON existentes.

Un estado histórico no se presenta como sonda viva.

### 8.2 Paridad de checks

- `--run-checks` ejecuta comandos explícitos y no hereda silenciosamente un
  `PYTEST_ADDOPTS` que reduzca la suite;
- la enumeración de tests es recursiva;
- el nombre “mypy strict” se usa únicamente si la configuración es estricta o
  se sustituye por una descripción honesta;
- coverage carga `.env` como datos. V2 mide primero línea y branch; fija un
  umbral inicial basado en evidencia fresca y un ratchet no decreciente. No
  declara branch coverage obligatorio antes de ese baseline;
- la auditoría de dependencias cubre las superficies realmente instaladas y
  probadas, no solo el grupo dev;
- los reportes sanitizan secretos y se escriben con permisos restrictivos;
- `config/quality_checks.json` será el manifiesto versionado de comandos,
  exclusiones, timeout y superficies. Un runner común lo consume localmente y
  desde CI;
- la paridad significa mismo manifiesto por intérprete disponible. No afirma
  que una máquina local reproduzca por sí sola la matriz Python 3.11/3.12 ni
  jobs de plataforma que solo existen en CI;
- CI y `atlas reality --run-checks` publican perfil, intérprete, manifiesto y
  exclusiones usados.

### 8.3 Aceptación de V

Fixtures sintéticos prueban cada celda `B/W/—/C`, la edad de historia y la
semántica de `unknown`. En particular, grafo obsoleto, ColdUpdate fallido y F2.6
pendiente no pueden desaparecer de `status_by_profile`/
`failures_by_profile`. Tests de compatibilidad prueban la proyección legacy y
la versión de schema. El runner usa entorno allowlisted y `ATLAS_HOME` temporal
para que configuración local no reduzca la suite.

## 9. Corte U — reconciliación y evidencia de producto UI

U se divide en U0 (topología/requisitos), U1 (contratos y harness), U2
(prototipos estrictamente necesarios) y U3 (comparación/disposición). U1–U3 son
condicionales al resultado de U0.

### 9.1 U0 — topología y requisitos

ADR-078 afirma que CodeOSS/VSCodium es el host desktop del Workbench y separa
Android; ADR-071 afirma que Linux y Android son plataformas duras. Como las
etiquetas documentales de aceptación no bastan, el operador confirmará:

- si la elección de CodeOSS/VSCodium fue informada y sigue vigente;
- si Android continúa como requisito obligatorio, objetivo posterior o queda
  fuera;
- si Mission Console debe vivir dentro del Workbench desktop, ser la proyección
  Android o constituir un producto adicional;
- qué flujos debe poder realizar sin terminal;
- qué compromisos de memoria, arranque, instalación y actualización importan;
- qué atributos de carácter visual son preferencias reales.

El baseline nulo —mantener las superficies existentes y no crear otra app— se
incluye siempre. Si CodeOSS/VSCodium se confirma, no se repite una competición
Flutter/Compose/Qt para desktop. Si no se confirma, desktop se reabre de forma
explícita con el host actual y un máximo de dos alternativas. Android se decide
por separado.

U0 produce filtros duros, un máximo de tres candidatos por superficie
incluyendo baseline/nulo, presupuesto aprobado y criterios de abandono. Un
candidato que falla plataforma obligatoria, seguridad, licencia, build release
o contrato backend no consume el vertical slice completo.

### 9.2 U1 — contratos antes de prototipos

La UI consume una Surface API estable y no duplica autoridad. Una proyección
Android que permita aprobar/denegar depende de un contrato separado de pairing,
canal cifrado autenticado, almacenamiento/revocación de credenciales y pérdida
de dispositivo. El bridge 7341 permanece loopback; el benchmark no lo expone a
la red ni improvisa HTTP remoto.

U1 versiona dataset, secuencia de interacción, estados de error y receipts
esperados. Si esos contratos no están estables, Android queda `BLOCKED` o
`DEFERRED` honestamente y U puede terminar sin elegir stack móvil.

### 9.3 U2 — vertical slice comparable

Solo cada candidato de la shortlist U0 que supere los filtros implementa el
mismo corte contra U1:

1. resumen de misiones;
2. detalle de tarea con stream de eventos;
3. aprobación o denegación gobernada con receipt visible;
4. vista de conocimiento suficientemente densa para probar navegación;
5. estados offline, degradado y error recuperable;
6. navegación por teclado, escalado y accesibilidad básica.

Si Android continúa siendo obligatorio y U1 está resuelto, al menos el flujo de
aprobación y el estado offline se ejecutan en un dispositivo Android real. Un
mock desktop no demuestra paridad móvil.

### 9.4 Harness común

Todos los candidatos usarán:

- mismo hardware, modo GPU y build release;
- dataset y secuencia de interacción versionados;
- cold start y warm start;
- RSS idle/activo y pico de build;
- frame pacing/jank, no solo FPS medio;
- tamaño de artefacto e instalación limpia;
- reconexión, pérdida de backend y reanudación;
- accesibilidad y escalado;
- licencia, packaging, actualización y mantenimiento por plataforma;
- comandos, raw logs y versiones conservados como artefactos.

El benchmark de cambio por agente usa el mismo prompt, contexto permitido,
tarea acotada, máximo de intentos, timeout y comandos de verificación para todos
los candidatos. Registra diff, tiempo, intentos, build y tests; no acepta una
opinión del agente como métrica.

Las mediciones anteriores se reproducen o se marcan no reproducibles. No se
mezclan cifras de iGPU, dGPU, debug y release en una misma tabla.

### 9.5 U3 — disposición

Atlas presenta una recomendación con evidencia, incertidumbres, falsificadores
y coste de rollback. El operador prueba solo los candidatos técnicamente
viables y confirma por separado:

1. topología, requisitos y plataformas vinculantes;
2. carácter y experiencia preferidos cuando la evidencia no determina una
   única alternativa.

La disposición puede ser seleccionar, preservar, diferir o rechazar una
superficie. Si produce un ADR, este incluye la confirmación explícita y los
artefactos medidos. Hasta entonces Flutter, Compose y Qt no son canon por
ADR-082; tampoco son necesariamente candidatos para todas las superficies.

## 10. Estrategia de pruebas

Cada corte empieza con tests que fallen por la causa reproducida:

- R: sockets ocupados, parseo inválido, estado/identidad, doble arranque,
  rollback parcial y readiness;
- C: consistencia ADR/registro/backlog, reconciliación de alcances, Golden Route
  e invalidación de claims supersedidos;
- G: checkout/wheel, bootstrap adversarial, symlinks y migración interrumpida;
- P: schema heredado, `legacy_unknown`, precedencia, corrupción y cierre de
  efectos;
- A: perfil seguro, PID/readiness, ventanas, ausencia de efectos, restauración
  incremental y rollback;
- V: cada celda de la matriz, `unknown`, caducidad, entorno contaminado e
  inventario recursivo;
- U: contratos/harness y criterios de aceptación antes de crear cada prototipo
  condicional.

Las pruebas dirigidas se ejecutan durante el desarrollo. Antes de cerrar cada
corte se ejecutan los checks proporcionales a su blast radius; antes de cerrar
el programa se exige suite completa, tipos, auditoría Merkle, build/install
smoke y perfiles de realidad aplicables.

Una prueba verde existente que no cubra la reproducción no cuenta como
evidencia de ausencia del defecto.

## 11. Entrega y commits

Los cortes se entregan en unidades revisables:

1. C1 — disposición canónica de ADR-082 y reconciliación de alcance.
2. R1 — exporter, configuración y proyección de estado.
3. R2 — lifecycle y rollback transaccionales.
4. R3 — límites systemd, readiness e instalador.
5. G1 — baseline package-owned y migración de gobernanza.
6. P1 — schema v2 y migrador dry-run.
7. P2 — precedencia y procedencia de permisos.
8. P3a — salud central; P3b — inventario ejecutable; P3c-n — cierre por familia
   de efectos.
9. A — activación controlada y recuperación de autonomía.
10. V1 — señales, matriz y compatibilidad JSON.
11. V2 — manifiesto común de checks y paridad CI.
12. V3 — auditoría de dependencias, secretos y coverage.
13. U0 — disposición de topología y requisitos.
14. U1/U2/U3 — contratos, candidatos y decisión solo cuando U0 los requiera.
15. F2.6 — ejecución separada y explícitamente autorizada tras el último ADR.

Los títulos son orientativos; no justifican mezclar subsistemas. Cada commit
incluye tests y la documentación directamente afectada. Los cambios previos del
operador permanecen fuera del staging.

## 12. Rollback y recuperación

- R conserva un interruptor para deshabilitar Prometheus y permite volver a la
  configuración anterior sin perder estado; la unidad instalada también tiene
  backup y rollback.
- C se revierte mediante otra disposición canónica, nunca borrando historia.
- G/P migran con backup no-follow, hash y dry-run; ante fallo mantienen
  denegados los efectos y conservan el original.
- V añade primero campos/perfiles sin romper consumidores JSON; cualquier
  cambio incompatible exige versión de schema.
- U mantiene los prototipos aislados hasta una disposición; diferir una
  superficie no obliga a conservar código candidato.

## 13. Riesgos y mitigaciones

- **Recuperar el daemon demasiado pronto:** mitigado manteniéndolo apagado hasta
  R3+G1+P3 y usando un primer smoke sin schedulers ni efectos.
- **Corregir el canon solo de forma cosmética:** mitigado por checks sobre ADR,
  backlog, registros, índices y claims derivados.
- **Borrar personalizaciones o preservar revocaciones obsoletas:** mitigado por
  schema separado, `legacy_unknown`, precedencia y migración con dry-run.
- **Hacer `reality` imposible de poner verde:** mitigado por perfiles y
  distinción entre dependencia requerida y opcional.
- **Reabrir por accidente una decisión desktop distinta:** mitigado por U0,
  confirmación directa y separación Workbench/Android/producto adicional.
- **Convertir el benchmark UI en otro concurso de una pantalla:** mitigado por
  shortlist acotada, contratos previos, flujos representativos y, si aplica,
  dispositivo Android real.
- **Expandir indefinidamente el programa:** mitigado por specs y planes
  separados, criterios de salida y commits pequeños.

## 14. Fuera de alcance

- elegir ahora un stack UI;
- cambiar el contenido constitucional de `config/governance.json`;
- ejecutar F2.6 sin autorización específica;
- instalar, materializar o saltarse la cuarentena de `sequential-thinking`;
- arreglar todos los documentos huérfanos o el backlog completo;
- introducir dependencias nuevas sin una decisión separada;
- mezclar los cambios existentes de `.gitignore` o `docs/fixtures/`.

## 15. Definición de terminado del programa

El programa termina cuando:

1. el daemon arranca bajo el gate A y permanece listo sin restart storm;
2. ADR-082 ya no es una aceptación vigente y su relación con ADR-071/ADR-078 y
   los work orders afectados está resuelta sin inventar intención del operador;
3. gobernanza no puede ser sustituida por una raíz ambiental y los permisos
   soportan revocación obligatoria, overlay explícito, migración ambigua segura
   y corrupción fail-closed en todos los efectos inventariados;
4. `atlas reality` y CI concuerdan para perfiles equivalentes;
5. U0 ha producido una disposición informada; si exige candidatos, U1–U3 han
   producido evidencia reproducible y decisión explícita, y si difiere o
   preserva una superficie no se fabrica trabajo adicional;
6. suite, tipos, auditoría, documentación y límites conocidos se entregan con
   evidencia fresca.

Ese estado marca `engineering_complete`. `operator_gate_complete` requiere
además que el operador autorice y F2.6 pase después del último ADR/disposición
que active el gate. Mientras falte esa autorización, el programa se reporta
honestamente como pendiente de gate humano y no como completamente terminado.
