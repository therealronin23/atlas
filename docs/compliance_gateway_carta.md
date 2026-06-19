# Osmosis Filter: capa obligatoria en el camino de cumplimiento

*Carta de presentación / nota técnica. Autor: Osmosis Project (un solo
desarrollador). Junio 2026.*

> **En una línea:** Proponemos una capa de cumplimiento siempre activa,
> interpuesta obligatoriamente entre el usuario y el modelo frontier, cuyo coste
> de operación asumimos nosotros como proveedor del filtro. El operador (Anthropic)
> no añade latencia de auditoría ni gestión de log — eso es nuestro problema.
> Lo que obtiene: un log verificable en ambas direcciones que convierte
> "ante la duda, apagón total" en acceso regulable con evidencia de cumplimiento
> demostrable ante regulador y usuario. El núcleo está construido y funciona;
> esto es la semilla, no el producto.

---

## El problema, en sus propias palabras

El 12 de junio de 2026 una directiva de control de exportación obligó a Anthropic
a suspender Fable 5 y Mythos 5 para todos los usuarios. Las dos razones públicas:

1. No se puede **distinguir en tiempo real** a un foreign national de un usuario
   doméstico — ante la duda, apagón total.
2. Se conoció un **método de bypass/jailbreak** del modelo.

El apagón no ocurrió porque el modelo sea peligroso para todos. Ocurrió porque
**no existía forma de garantizar quién lo usa ni de demostrar que no se abusa de
él**. El problema no es el modelo; es la ausencia de una capa de identidad
verificable + cumplimiento demostrable.

---

## La observación que os concierne directamente

Hay un gap estructural que vosotros no podéis cerrar por construcción:

Anthropic es **a la vez** el proveedor del modelo y el operador del clasificador
de seguridad (CC++). Eso significa que cuando decís "inspeccionamos el contenido
solo cuando hay causa", el usuario no tiene forma de verificarlo. No porque
mintáis — sino porque el log de inspecciones está en vuestras manos y solo en
las vuestras. El conflicto de interés no es de intención; es estructural.

Un sistema externo, con un log verificable en ambos sentidos, cierra precisamente
ese gap — el que vosotros no podéis cerrar siendo juez y parte.

---

## La propuesta, en una frase

Un **filtro osmótico obligatorio en el camino**: toda petición al modelo pasa por
una capa que co-firma, registra, y verifica en ambas direcciones — antes de llegar
al modelo y antes de llegar al usuario. La capa es siempre activa, no opcional.
El coste de infraestructura, mantenimiento y auditoría de esa capa lo asumimos
nosotros. Lo que obtenéis: log verificable por regulador y usuario que convierte
"ante la duda, apagón total" en **acceso regulable con evidencia de cumplimiento
continua y auditable** — incluida la parte que hoy no puede verificar nada por sí
misma: el usuario.

Dos problemas permanecen abiertos en este diseño y los declaramos explícitamente:
la *faithfulness conductual* (que el comportamiento del modelo en producción
coincida con su comportamiento bajo sonda) y la protección *split-view* sin
witnesses externos (RFC 9162, gossip de STH). El núcleo cierra la omisión; los
witnesses y la equivalencia conductual formal son trabajo futuro.

---

## Por qué la detección no es el eje (honestidad por delante)

El estado del arte en junio 2026 es claro: ningún sistema — incluyendo el mejor
en producción, que es el vuestro (CC++) — reclama robustez contra un adversario
que adapta su ataque a la defensa concreta. *The Attacker Moves Second*
(arXiv:2510.09023) lo demostró formalmente: ataques adaptativos superan >90% de
las defensas existentes.

**Esta propuesta no promete detectar el jailbreak. Promete encarecer la campaña
y hacerla verificablemente inocultable.** Son objetivos distintos y el segundo
es alcanzable; el primero no lo es de forma garantizada hoy para nadie.

---

## Las dos aportaciones que no existen en ningún sistema desplegado

### 1. Verificabilidad mutua del log

Un único log inmutable (Merkle, RFC 9162) prueba dos cosas a dos partes que no
se fían entre sí:

- Al **regulador/proveedor**: cada abuso detectado y bloqueado.
- Al **usuario**: que *cada* inspección de su contenido estuvo precedida por una
  causa registrada — prueba de que no fue inspeccionado más allá de lo necesario.

La clave técnica: Merkle prueba integridad (lo que está no se alteró), pero NO
completitud (no prueba que no falta nada). Este sistema resuelve el problema de
completitud mediante **co-firma del cliente con secuencia monótona**: una laguna
en la secuencia es detectable por el propio usuario. El operador no puede
inspeccionar sin registrar porque el registro va atado a un request co-firmado
cuya secuencia el cliente vigila.

Límite honesto: la protección contra *split-view* (mostrar logs distintos a
regulador y usuario) requiere witnesses externos (RFC 9162, gossip de STH). Esa
red no está desplegada — es el siguiente nivel del ecosistema. La garantía
implementada hoy es la detección de omisión por el propio usuario, que ya es
algo que ningún sistema publicado ofrece.

Implementado: módulo de transparencia con pruebas específicas. El estado actual
de la suite no se declara a mano en esta carta; se verifica con
`PYTHONPATH=src atlas reality --run-checks --include-browser --json`.

### 2. Métrica de campaña falsable (lo que CC++ no tiene por diseño)

CC++ mide por intento. Eso tiene un límite fundamental: el adversario adaptativo
re-optimiza entre intentos y las tasas colapsan. Este sistema mide por campaña:

- **C_attempts**: intentos co-firmados registrados antes del primer bypass —
  observable directamente del log, sin inferencia.
- **K_attribution**: ≥3 intentos consecutivos con similitud de patrón >0.7 →
  campaña flagged con identidad co-firmada.
- **Criterio falsable**: la defensa fue eficaz si el atacante necesitó
  C_attempts ≥ K_attribution antes del bypass. Si el bypass ocurre en intento 1,
  la capa falló — y el log lo prueba.

Ningún sistema publicado tiene esta métrica porque ninguno tiene el log de
completitud verificable por el usuario que la hace posible.

**Actualización junio 2026 — módulo de inmunidad operativo:** implementa afinidad maduración 
sobre la capa 5: hipermutación semántica de patrones de defensa (no ruido léxico) + selección 
clonal con scoring LLM + promoción vía Decider. La mutación es conceptual —
reformulaciones que mantienen la semántica defensiva mientras introduce diversidad real. El 
entrenamiento adversarial tiende a sobreajustarse a distribuciones de ataque estrechas; CHASE 
(arXiv:2606.05523) lo aborda con co-evolución, pero requiere que el atacante mantenga diversidad 
de técnicas — lo que solo una fuente externa puede garantizar.

---

## El sistema completo: cuatro capas de defensa, honestidad sobre cada una

*(Síntesis técnica desarrollada en §8 del paper `paper_subject_enforced_completeness.md`.)*

| Capa | Qué hace | Límite honesto |
|---|---|---|
| 1. Filtro (CC++-style) | corta ruido y ataques conocidos | bypass alto contra adaptativo |
| 2. Polimorfismo por sesión | randomiza hiperparámetros de decodificación por sesión (FlexLLM); invalida jailbreaks precomputados; salt registrado en log | sin acceso a activaciones del modelo (API externa): protección más débil que salting sobre dirección de rechazo |
| 3. Señuelo (solo tras causa confirmada) | genera evidencia forense; invierte la carga de certeza al atacante | cae ante sonda verificable en dominio ejecutable; vale por la causa que genera, no por engañar al adversario serio |
| 4. **Log de campaña verificable** | hace la serie de intentos inocultable; métrica C_attempts/K_attribution; encarece la campaña | no detecta el intento individual |
| 5. **Memoria inmune con diversidad externa** | aprende de cada exposición; el organismo de conocimiento inyecta ataques reales del exterior | no esterilizante ante ataque verdaderamente novel; la inyección de diversidad aún pendiente |

**Sobre la capa 5 y por qué importa específicamente para vosotros:** los sistemas
de co-evolución atacante-defensor publicados en 2026 (CHASE, arXiv:2606.05523)
muestran que el entrenamiento adversarial se sobreajusta a distribuciones de ataque
estrechas — el defensor se estanca en lo que ya vio — y que la co-evolución
requiere que el atacante mantenga diversidad de técnicas. CC++ tiene este problema por construcción: aprende de vuestro
tráfico, pero si los ataques nuevos no aparecen en ese tráfico, no los conoce
hasta que ocurren. Un organismo de conocimiento que inyecta técnicas de ataque
externas (papers, feeds, CVEs) antes de que lleguen al tráfico real es la
mitigación estructural. Ningún paper publicado tiene esto porque ninguno tiene un
organismo de conocimiento conectado a su sistema inmune.

---

## Alineación con EU AI Act (agosto 2026)

El mapeado completo artículo-por-artículo está en `docs/eu_ai_act_mapping.md`. Aquí
resumimos los tres artículos más directamente relevantes para vosotros como proveedor
GPAI con riesgo sistémico, con estados honestos:

- **Art. 12 (Record-keeping)** — Estado: implementado (✅). El núcleo es
  el mecanismo técnico más directo: log automático, tamper-resistant, verificable por
  ambas partes, diseño append-only con retención indefinida. La ley exige mínimo 6
  meses; la arquitectura no tiene techo. Límite: la política de retención mínima es
  configuración del operador, no propiedad del mecanismo.

- **Art. 13 (Transparency)** — Estado: implementado / parcial (✅/🟡). La
  verificabilidad mutua (el usuario detecta omisiones unilateralmente, sin confiar en el
  operador) transforma "nos creéis bajo palabra" en "el usuario puede probar". Límite
  honesto: falta UI activa que informe al usuario final en cada sesión; hoy la
  verificación requiere que el usuario consulte el log activamente.

- **Art. 53 (Systemic risk — red-teaming)** — Estado: parcial (🟡). El organismo de
  conocimiento inyecta técnicas de ataque externas antes de que lleguen al
  tráfico real. CC++ solo puede aprender de vuestro propio tráfico; el auto-juego
  produce sobreajuste a distribuciones de ataque estrechas, documentado en CHASE
  (arXiv:2606.05523). Límite honesto: el cableado del organismo de conocimiento → panel 
  adversarial está diseñado pero no completado todavía.

Ningún sistema en producción combina los tres con verificabilidad mutua. Esa es la
aportación concreta, no una promesa de cumplimiento total.

---

## Lo que esto NO es

- No propongo interponer un binario externo en el path de vuestro modelo bajo vuestra
  gestión operativa. La capa es nuestra responsabilidad, no vuestra.
- No afirmo detección garantizada por intento. Nadie puede garantizarla hoy (*The
  Attacker Moves Second*, arXiv:2510.09023). La métrica es de campaña: C_attempts y
  K_attribution, falsables y medibles desde el log.
- No es un producto validado a escala enterprise. Es la arquitectura y el núcleo
  construido, con estado verificable mediante `atlas reality`; las capas que
  faltan están documentadas honestamente en ADRs.
- No resolví el binding de identidad (KYC real para foreign nationals). Eso es operativo
  y legal, no código. La capa de filtro presupone que la identidad ya está verificada por
  vosotros.
- El witness network (protección split-view) no está desplegado: es el siguiente nivel
  del ecosistema, no la demo de hoy. La garantía implementada hoy es la detección de
  omisión por el propio usuario — ya es algo que ningún sistema publicado ofrece.
- La faithfulness conductual (que el comportamiento bajo sonda prediga el comportamiento
  en producción) es un problema abierto en este diseño y en la literatura. La capa 4
  (canary framework) es el avance activo hacia ese problema; no lo cierra.

---

## Por qué os lo enseño

No para vender un producto. Para dos cosas concretas:

**1. Señalar el gap que existe y que no podéis cerrar solos.**
El conflicto de interés estructural (sois a la vez proveedor y clasificador) hace
imposible que ofrezcáis verificabilidad al usuario sobre vuestras propias
inspecciones. No es un problema de intención — es de arquitectura. Un sistema
externo verificable es la única solución a ese problema, y ese sistema no existe
en producción en ningún lugar hoy.

**2. Mostrar el razonamiento, no el producto.**
Un solo desarrollador, al día siguiente del apagón de Fable 5/Mythos 5,
identificó las dos causas técnicas, diseñó una respuesta arquitectónica con el
eje correcto (verificabilidad mutua, no detección perfecta), y construyó el
núcleo que prueba que el mecanismo de completitud es implementable. Lo que
tenemos es la semilla — el log verificable funcionando dentro
de un organismo que puede aprender de cada campaña que ese log hace inocultable.
Si la forma de pensar os resulta útil, hablemos.

---

*Demo (~2 min disponible): una sesión legítima cuyo log prueba cero inspecciones
de contenido, y una sesión con abuso catalogado detectado, bloqueado y registrado
— ambas sobre la misma cadena inmutable, mostrando la prueba en ambas direcciones.
Núcleo en módulo de transparencia del Osmosis reference implementation; estado
actual verificable con `atlas reality`. Arquitectura completa de cuatro capas en §8 de
`docs/paper_subject_enforced_completeness.md` y en `docs/eu_ai_act_mapping.md`.*

*Fuentes del incidente: declaraciones de Anthropic y cobertura de Time, CNBC, Al
Jazeera, Fortune (13-jun-2026).*
