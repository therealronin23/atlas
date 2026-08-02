# Programa de recuperación de integridad de Atlas

- **Estado:** aprobado por el operador para especificación; implementación aún no autorizada
- **Fecha:** 2026-08-02
- **Baseline inspeccionado:** `813d0b8e7a34b94600840231c4ef4a873fbe9bec`
- **Ámbito:** runtime, canon de decisiones, fronteras de confianza, realidad/CI y elección de UI T2.1
- **No modifica:** `config/governance.json`

## 1. Resultado

Atlas detiene la construcción sobre afirmaciones no demostradas y recupera una
base operativa y decisional verificable antes de continuar T2.1.

ADR-082 no constituye una elección informada del operador. El operador confirmó
el 2026-08-02 que aceptó una sugerencia sin haber comparado conscientemente los
prototipos. Por tanto:

1. Flutter deja de ser una decisión canónica válida.
2. Ningún stack alternativo pasa a ser ganador por descarte.
3. T2.1 queda abierto hasta reproducir evidencia comparable y obtener una
   decisión explícita del operador.
4. F2.6 permanece pendiente, pero no se ejecuta contra un canon que sabemos
   incorrecto. Se ofrecerá de nuevo al operador después de reparar ese canon.
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
- el grafo estructural está `FRESH` y coincide con el HEAD;
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
   |
   +--> R. Recuperación del runtime
   |
   +--> C. Reparación del canon --> oferta explícita de F2.6
             |
             v
       T. Fronteras de confianza
             |
             v
       V. Realidad y CI honestos
             |
             v
       U. Evaluación UI representativa --> decisión explícita del operador
```

R y C son cortes independientes y pueden prepararse en paralelo, pero se
integran en ese orden para recuperar primero la operación local. T y V no se
declaran cerrados hasta que sus checks prueben el comportamiento adversarial.
U no empieza a construir la aplicación definitiva: produce evidencia y una
decisión válida.

## 5. Corte R — recuperación operativa del runtime

### 5.1 Contrato de configuración

- `ATLAS_PROMETHEUS` conserva un modo deshabilitado por defecto.
- host y puerto se parsean mediante funciones validadas; un valor inválido no
  genera un traceback sin contexto.
- el exporter se considera opcional salvo que exista un modo explícito
  `required`. El modo opcional contiene `EADDRINUSE` y otros fallos de arranque,
  registra estado degradado y permite continuar el servicio.
- no se asigna ahora un puerto “libre” por intuición. La migración del workspace
  comprueba listener, propietario y readiness antes de seleccionar un puerto
  dedicado y alinea scraper, configuración y documentación.

### 5.2 Lifecycle transaccional

`ServiceRunner.start()` mantendrá un registro ordenado de componentes adquiridos.
Ante cualquier excepción fatal:

1. registra `service.start_failed` con el componente y error sanitizado;
2. revierte en orden inverso solo los componentes realmente iniciados;
3. deja `_running=False` y un estado coherente aunque `_started` nunca llegara a
   ser verdadero;
4. vuelve a elevar el fallo cuando el componente sea obligatorio;
5. conserva el servicio si el único fallo pertenece a un componente opcional.

`stop()` será idempotente y limpiará estado parcial. No dependerá de una única
bandera que solo se activa al final del arranque.

### 5.3 systemd y readiness

- la unidad limitará ráfagas de reinicio para que un fallo persistente no genere
  miles de procesos y trazas;
- readiness verificará el proceso y cada endpoint obligatorio habilitado;
- un endpoint ajeno que responda en el puerto esperado no contará como Atlas;
- el instalador distinguirá `active` transitorio de readiness estable.

### 5.4 Aceptación de R

- prueba de colisión real con un socket temporal ya ocupado;
- prueba de puerto inválido;
- prueba de exporter sano y respuesta `atlas_up 1`;
- prueba de rollback tras fallo en cada etapa relevante del arranque;
- `stop()` repetido no falla ni deja threads propios vivos;
- smoke de systemd demuestra contador de reinicios estable y readiness de
  Atlas;
- solo entonces se reactiva `atlas-core.service`.

## 6. Corte C — reparación del canon de decisiones

### 6.1 Disposición de ADR-082

ADR-082 no se elimina. Se preserva como evidencia de una decisión inválidamente
cerrada y recibe una anotación mínima de supersesión. Un ADR posterior:

- declara que no existe stack ganador;
- registra la confirmación del operador sin reinterpretarla como preferencia de
  stack;
- enumera las contradicciones de evidencia;
- reabre T2.1 y sus dependientes;
- define el benchmark representativo necesario para decidir;
- no convierte Qt en ganador por tener mejores cifras en el micro-PoC Linux.

El backlog, registro de decisiones, índice de ADR y cualquier estado derivado se
actualizan en la misma unidad lógica. No se reescribe el pasado para fingir que
ADR-082 nunca existió.

### 6.2 F2.6

F2.6 sigue siendo una sesión LLM real y costosa. El programa no la ejecuta
silenciosamente ni altera su ledger para volverla `current`.

Después de integrar la supersesión y comprobar el canon:

1. se vuelve a consultar `atlas f26 status --json`;
2. se presenta al operador la notificación exacta vigente;
3. solo una autorización específica dispara `atlas f26 run --json`;
4. un fallo abre trabajo correctivo y exige repetir la rúbrica completa.

### 6.3 Aceptación de C

- ninguna fuente canónica afirma que Flutter sea definitivo;
- T2.1, T2.2 y T2.3 no heredan un stack no elegido;
- las cifras históricas se etiquetan por procedencia y alcance;
- Android figura como requisito por confirmar, no como plataforma probada;
- sanitation e índices encuentran la nueva disposición;
- búsquedas de claims antiguos no encuentran una aceptación vigente sin enlace
  a su supersesión.

## 7. Corte T — fronteras de confianza

### 7.1 Gobernanza

Se separan tres conceptos hoy confundidos:

- **baseline constitucional:** artefacto versionado junto al código que lo
  interpreta;
- **snapshot runtime:** copia verificable usada por el workspace;
- **migración:** operación explícita y auditada entre versiones.

Reglas:

1. `ATLAS_CORE_ROOT` o cualquier ruta de datos no puede seleccionar por sí sola
   un baseline constitucional alternativo.
2. En el primer bootstrap se materializa el baseline distribuido y se registra
   su hash/procedencia antes de permitir efectos.
3. En arranques posteriores, una ausencia o divergencia bloquea acciones
   gobernadas y ofrece una migración explícita; no sobrescribe automáticamente.
4. La inicialización de auditoría necesaria para registrar el preflight ocurre
   antes de cualquier copia o migración con efecto.
5. Este corte no cambia el contenido normativo de `config/governance.json`.

### 7.2 Permisos

El fichero efectivo deja de depender de una unión monotónica sin procedencia.
El modelo será:

```text
baseline versionado
  + grants locales explícitos del operador
  - denies/revocaciones locales explícitas
  = perfil efectivo con procedencia por entrada
```

Una entrada retirada del baseline desaparece del perfil efectivo, salvo que el
operador la haya concedido explícitamente como override local. Actualizar Atlas
no borra personalizaciones; tampoco convierte residuos del baseline anterior en
personalizaciones.

Los campos `absolute_blocks` y `system_read_allowed` tendrán una sola autoridad:
o se cargan y validan desde configuración inmutable, o se eliminan del fichero
sincronizado y permanecen constantes en código. No se mantiene una configuración
decorativa que no afecte al runtime.

Si el perfil falta, está corrupto o no valida:

- escrituras, shell, red y efectos externos quedan denegados;
- el runtime se marca degradado con causa estructurada;
- solo se permite el diagnóstico local de lectura expresamente definido por el
  baseline inmutable;
- no se repara el fichero automáticamente con datos ambiguos.

### 7.3 Aceptación de T

- un `ATLAS_CORE_ROOT` adversarial no altera gobernanza;
- una divergencia del snapshot produce bloqueo y evidencia, no overwrite;
- retirar un comando del baseline lo revoca;
- un grant local explícito sobrevive a una actualización;
- un deny local prevalece;
- YAML corrupto niega todos los efectos;
- cada decisión efectiva indica si proviene de baseline, grant o deny;
- los tests cubren symlinks, rutas absolutas, Git read-only y cadenas shell ya
  protegidas para evitar regresiones laterales.

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
- `succession`: canon e índices frescos y F2.6 vigente.

Los providers opcionales muertos no bloquean indiscriminadamente. Sí bloquean
un perfil que los declare requeridos. Un estado histórico no se presenta como
sonda viva.

### 8.2 Paridad de checks

- `--run-checks` ejecuta comandos explícitos y no hereda silenciosamente un
  `PYTEST_ADDOPTS` que reduzca la suite;
- la enumeración de tests es recursiva;
- el nombre “mypy strict” se usa únicamente si la configuración es estricta o
  se sustituye por una descripción honesta;
- coverage carga `.env` como datos, define un umbral versionado y mide branches
  cuando el proyecto lo adopte;
- la auditoría de dependencias cubre las superficies realmente instaladas y
  probadas, no solo el grupo dev;
- los reportes sanitizan secretos y se escriben con permisos restrictivos;
- CI y `atlas reality --run-checks` publican qué perfil y exclusiones usaron.

### 8.3 Aceptación de V

Fixtures sintéticos prueban que cada estado bloquea únicamente los perfiles
declarados. En particular, grafo obsoleto, ColdUpdate fallido y F2.6 pendiente
no pueden desaparecer de `overall_status`/`strict_failures`. La salida JSON
permanece estable y las adiciones son compatibles o cuentan con migración.

## 9. Corte U — nueva decisión de stack UI

### 9.1 Requisitos antes de prototipos

El operador confirmará primero:

- si Android sigue siendo requisito obligatorio o un objetivo posterior;
- qué flujos debe poder realizar sin terminal;
- qué compromisos de memoria, arranque, instalación y actualización importan;
- qué atributos de carácter visual son preferencias reales.

No se pedirá al operador que elija tecnología por nombre antes de ver el
resultado.

### 9.2 Vertical slice comparable

Cada candidato que sobreviva los filtros duros implementará el mismo corte,
contra contratos existentes y sin duplicar autoridad backend:

1. resumen de misiones;
2. detalle de tarea con stream de eventos;
3. aprobación o denegación gobernada con receipt visible;
4. vista de conocimiento suficientemente densa para probar navegación;
5. estados offline, degradado y error recuperable;
6. navegación por teclado, escalado y accesibilidad básica.

Si Android continúa siendo obligatorio, al menos el flujo de aprobación y el
estado offline se ejecutan en un dispositivo Android real. Un mock desktop no
demuestra paridad móvil.

### 9.3 Harness común

Todos los candidatos usarán:

- mismo hardware, modo GPU y build release;
- dataset y secuencia de interacción versionados;
- cold start y warm start;
- RSS idle/activo y pico de build;
- frame pacing/jank, no solo FPS medio;
- tamaño de artefacto e instalación limpia;
- reconexión, pérdida de backend y reanudación;
- accesibilidad y escalado;
- coste de cambio representativo realizado por un agente nuevo;
- licencia, packaging, actualización y mantenimiento multiplataforma;
- comandos, raw logs y versiones conservados como artefactos.

Las mediciones anteriores se reproducen o se marcan no reproducibles. No se
mezclan cifras de iGPU, dGPU, debug y release en una misma tabla.

### 9.4 Decisión

Atlas presenta una recomendación con evidencia, incertidumbres, falsificadores
y coste de rollback. El operador prueba las aplicaciones reales y confirma dos
cosas por separado:

1. requisitos/plataformas que son vinculantes;
2. carácter y experiencia preferidos entre candidatos técnicamente viables.

El nuevo ADR incluye esa confirmación explícita y los artefactos medidos. Hasta
entonces, Flutter, Compose y Qt son candidatos o descartes justificados, no
canon.

## 10. Estrategia de pruebas

Cada corte empieza con tests que fallen por la causa reproducida:

- R: sockets ocupados, parseo inválido, rollback parcial y readiness;
- C: consistencia de ADR/registro/backlog e invalidación de claims supersedidos;
- T: bootstrap adversarial, revocaciones, overrides y corrupción;
- V: matriz sintética de perfiles, entorno contaminado e inventario recursivo;
- U: harness y criterios de aceptación antes de ampliar prototipos.

Las pruebas dirigidas se ejecutan durante el desarrollo. Antes de cerrar cada
corte se ejecutan los checks proporcionales a su blast radius; antes de cerrar
el programa se exige suite completa, tipos, auditoría Merkle, build/install
smoke y perfiles de realidad aplicables.

Una prueba verde existente que no cubra la reproducción no cuenta como
evidencia de ausencia del defecto.

## 11. Entrega y commits

Los cortes se entregan en unidades revisables:

1. `fix(runtime): make optional exporters and startup lifecycle resilient`
2. `docs(decision): supersede unsupported mission console stack choice`
3. `fix(governance): separate trusted baseline from runtime state`
4. `fix(permissions): add provenance-aware baseline and overrides`
5. `fix(reality): enforce explicit readiness profiles`
6. `ci: align local checks, audit and coverage with CI`
7. `test(ui): add representative cross-platform decision harness`
8. `docs(decision): record operator-selected mission console stack`

Los títulos son orientativos; no justifican mezclar subsistemas. Cada commit
incluye tests y la documentación directamente afectada. Los cambios previos del
operador permanecen fuera del staging.

## 12. Rollback y recuperación

- R conserva un interruptor para deshabilitar Prometheus y permite volver a la
  configuración anterior sin perder estado.
- C se revierte mediante otra disposición canónica, nunca borrando historia.
- T migra perfiles con backup, hash y dry-run; ante fallo mantiene denegados los
  efectos y conserva el original.
- V añade primero campos/perfiles sin romper consumidores JSON; cualquier
  cambio incompatible exige versión de schema.
- U mantiene los prototipos aislados hasta seleccionar stack; no entra código
  candidato en la autoridad de runtime.

## 13. Riesgos y mitigaciones

- **Recuperar el daemon demasiado pronto:** mitigado por prueba de bind,
  readiness propia y observación del contador de reinicios antes de declararlo
  activo.
- **Corregir el canon solo de forma cosmética:** mitigado por checks sobre ADR,
  backlog, registros, índices y claims derivados.
- **Borrar personalizaciones al arreglar permisos:** mitigado por procedencia y
  migración con dry-run.
- **Hacer `reality` imposible de poner verde:** mitigado por perfiles y
  distinción entre dependencia requerida y opcional.
- **Convertir el benchmark UI en otro concurso de una pantalla:** mitigado por
  flujos representativos, estados de fallo y, si aplica, dispositivo Android
  real.
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

1. el daemon arranca y permanece listo sin restart storm;
2. ADR-082 ya no es una aceptación vigente y F2.6 se ha resuelto sobre el canon
   reparado;
3. gobernanza no puede ser sustituida por una raíz ambiental y los permisos
   soportan revocación, override explícito y corrupción fail-closed;
4. `atlas reality` y CI concuerdan para perfiles equivalentes;
5. existe evidencia UI reproducible sobre los requisitos confirmados;
6. el operador ha probado los candidatos viables y ha tomado una decisión
   explícita registrada;
7. suite, tipos, auditoría, documentación y límites conocidos se entregan con
   evidencia fresca.
