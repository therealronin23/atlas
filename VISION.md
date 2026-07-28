# Vision — Atlas Definitive Candidate

## El problema

Los asistentes actuales suelen intercambiar comodidad por soberanía. El
contexto se pierde entre sesiones, los proveedores se convierten en autoridad,
las herramientas acumulan permisos, la investigación se confunde con verdad y
la automatización produce efectos que después nadie puede explicar, deshacer o
auditar.

Atlas existe para que una persona pueda ampliar su capacidad cognitiva sin
ceder el control de su memoria, su infraestructura, sus decisiones ni su
historia operativa.

## North star

Una intención expresada una sola vez se convierte en una misión durable:
Atlas recupera contexto verificable, propone un plan, selecciona modelos y
herramientas, explica riesgos, obtiene la autoridad necesaria, ejecuta en un
entorno acotado, prueba el resultado, deja evidencia, aprende sin contaminar la
memoria y puede recuperar el estado anterior.

La persona no administra una colección de agentes. Gobierna un sistema
coherente que sabe:

- qué es un hecho y qué es una hipótesis;
- qué puede hacer y qué requiere permiso;
- qué parte está simulada, configurada o realmente viva;
- de dónde procede cada decisión;
- cómo detenerse, revertir y continuar.

## Experiencia final

Atlas se presenta como un Product OS, no como una ventana de chat:

- una superficie dedicada para Linux y otra para Android;
- una barra universal que convierte intención en misiones gobernadas;
- presencia ambiental que muestra estado, riesgo, espera y actividad sin
  ocultar autoridad;
- workbenches líquidos que aparecen según el objetivo;
- continuidad local entre sesiones, dispositivos y nodos;
- vistas de conocimiento y evidencia que permiten inspeccionar por qué Atlas
  cree algo;
- aprobación humana situada justo antes del efecto relevante;
- recuperación y auditoría accesibles como capacidades de primer nivel.

Las superficies proyectan estado; no se convierten en dueñas de Task, Memory,
Policy, Evidence ni Execution.

## Soberanía local-first

El estado durable, la política, la memoria privada, la evidencia y el control
de ejecución tienen una ruta local. Un modelo externo es un proveedor
reemplazable, no un centro de autoridad. La ausencia de red degrada capacidad,
no identidad ni gobernanza.

`local-first` no significa aislamiento dogmático. Atlas puede usar proveedores,
servicios y nodos externos cuando aportan valor medido, siempre que existan:

- minimización de datos;
- clasificación de sensibilidad;
- contrato de capacidad;
- timeout y cancelación;
- recibo y atribución;
- alternativa o degradación;
- revocación y rollback.

## Distribución

Atlas puede extenderse a nodos, dispositivos y pares. La distribución comparte
capacidades y propuestas, no permisos implícitos. Cada boundary declara
identidad, autoridad, datos, protocolo, tiempo de vida y evidencia.

Hermes ocupa una línea diferenciada: interpreta y propone desde el exterior;
Atlas decide y ejecuta bajo sus autoridades. Un despliegue histórico no prueba
un par vivo.

## Autoconstrucción

Atlas puede estudiarse y mejorarse, pero no puede legitimarse a sí mismo.
Foundry construye candidatos en aislamiento; Golden Route enlaza misión,
worktree, pruebas, riesgos, gate, decisión, resultado y recibo. El proponente
no promociona su propio cambio. Una mejora aprende solo después de evidencia
independiente y conserva rollback.

La autoconstrucción no es mutar silenciosamente el checkout vivo ni descargar
software remoto y ejecutarlo por confianza.

## Confianza

La confianza se compone de propiedades observables:

- autoridad explícita;
- mínimo privilegio;
- procedencia de fuente, claim y decisión;
- aislamiento y fail-closed;
- pruebas y evaluación adversarial;
- evidencia Merkle;
- estados que distinguen código, wiring, configuración y runtime;
- recuperación no dependiente del mismo modelo que falló.

Una respuesta elocuente no es evidencia. Un test unitario no es un servicio
vivo. Un grafo semántico no es una base automática de hechos.

## Aprendizaje y conocimiento

Atlas conserva continuidad sin convertir cada conversación en verdad global.
La memoria privada se clasifica, resume y destila antes de compartirse. El
conocimiento mantiene claim, fuente, contexto temporal, contradicción y nivel
de confianza. El grafo estructural describe el repositorio; el grafo semántico
propone relaciones que deben verificarse.

La investigación externa entra como material no confiable. Atlas asimila una
capacidad solo después de disección, licencia/procedencia, vetting, prueba
acotada, comparación, decisión y recibo.

## Producto y programas

Los trece programas de `PROGRAMS.md` son líneas permanentes. Product OS no
absorbe el núcleo; Canon no absorbe lo difícil de clasificar; Security no se
convierte en dueño de toda ejecución; Membrane/Osmosis no desaparece tras
promover una sola idea.

ADR-078 fija Atlas Engineering Workbench como primer producto completo y una
línea CodeOSS/VSCodium como host de escritorio: se reutilizan las capacidades
útiles de Void y los contratos/patrones ACP de Zed sin clonar sus autoridades
ni reescribir lo que ya existe. Es una decisión de arquitectura y linaje, no
una afirmación de producto construido.

El mapa definitivo de memoria, el boundary Mission/Task, la amplitud exacta
del corte integral del Workbench y la proyección Android siguen requiriendo
diseño y gates posteriores. `atlas-shell` permanece como arnés de validación.
Hasta demostrar un recorrido real y obtener aceptación explícita, ningún
arnés, fork, prototipo o slice parcial se presenta como producto aceptado.

## Líneas no negociables

- soberanía y control local;
- aprobación humana para sensibilidad alta;
- efectos auditables y reversibles;
- proveedores reemplazables;
- arquitectura distribuida sin autoridad difusa;
- Hosted antes de Native;
- Wave 5 condicionada;
- auto-adopción remota ejecutable bloqueada;
- selección y asimilación sin clonación;
- verdad separada de propuesta, código, configuración y runtime;
- Membrane/Osmosis y auditoría bilateral como programa permanente;
- operador como única autoridad de aceptación constitucional.
