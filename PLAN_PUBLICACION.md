# PLAN COMPLETO — arXiv, sellado, outreach y siguiente paso

> Documento maestro. Todo lo hablado, paso a paso, sin dejarse nada.
> Fecha: 2026-06-20. Autor: Tomás Asín González.
> Regla de oro: **el paper YA está bien. No tocarlo más.**

---

## 0. ESTADO ACTUAL (qué está hecho y verificado)

- ✅ Paper completo y verídico: `docs/paper_subject_enforced_completeness.{pdf,tex,md}` (17 págs).
- ✅ **Citas verificadas una por una** (vía WebFetch): las 6 referencias 2025/2026 EXISTEN.
  Corregidos 3 metadatos (attacker2024: autores/año/título; aegis: "Enforcement"; scitt-refusal:
  título). Comillas clave (Sello §8.1, SCITT §1.3/3.6/7.1) confirmadas literales.
- ✅ Sellado OpenTimestamps (OTS) — **pendiente de confirmación Bitcoin** (ver §3).
- ✅ Firma GPG de autoría (ver §3).
- ✅ Backup en remoto privado: github.com/therealronin23/atlas.
- ✅ Línea de divulgación de asistencia de IA añadida (honestidad).
- ✅ Demos reproducibles + reportes (ver §5).
- ✅ Roadmap futuro registrado (ver §6).

**Veredicto honesto (convergente GPT + Grok + Claude):** trabajo sólido + honesto; la
contribución central (completitud verificable) es estrecha y defendible; el riesgo es que un
revisor la vea "incremental". No es humo. Verídico.

---

## 1. SUBIR A arXiv — pasos exactos

### 1.1 Arreglar la cuenta (te bloqueó por esto)
1. Entra en tu cuenta arXiv → **"Change User Information"**.
2. **Verifica el email**: busca el correo de confirmación de arXiv en `tomas.asin.gonzalez@gmail.com`
   (mira spam). Pulsa el enlace. Si no llegó, dale a **reenviar verificación**.
3. **Afiliación**: pon **"Independent Researcher"** (no necesitas universidad).
4. **Nombre**: First = `Tomás`, Last = `Asín González` (acentos correctos).
5. Guarda.

### 1.2 Endorsement (necesario para cs.CR) — ver §2 para a quién escribir
1. En arXiv pulsa **"request endorsement"** → copia tu **código** (tipo `ABCD12`) y el **enlace**.
2. Manda el mensaje de §2 a 2-3 personas (IMDEA primero).
3. Cuando alguien te avale, sigue.

### 1.3 Licencia
- Elige **`CC BY`** (Creative Commons Attribution). Máxima difusión, conservas copyright,
  te citan siempre. (Es irrevocable; para ti es lo correcto.)

### 1.4 Categorías
- **Archive:** `cs`
- **Primary:** `cs.CR` (Cryptography and Security)
- **Cross-list:** `cs.CY` (Computers and Society). Opcional 2ª: `cs.LG`.

### 1.5 Qué archivo subir
- **Recomendado (a prueba de fallos): solo el PDF** →
  `docs/paper_subject_enforced_completeness.pdf` y nada más.
- (Alternativa "fuente": `paper_subject_enforced_completeness.tex` + `.bbl`. Más "pro" pero
  puede dar errores de compilación en arXiv.)
- **NO subir:** `.aux .log .out .toc .blg .bib .html .md .ots`, ni `src/`, `scripts/`, ni `.env`.

### 1.6 Abstract para el formulario (copiar-pegar)
> Key transparency systems such as CONIKS and the IETF keytrans drafts let users monitor their
> own entries in an append-only log and detect operator equivocation without relying on global
> monitors. We transfer this pattern to a new domain: completeness of AI content-inspection logs.
> For a given subject's request stream, we show that completeness — whether every inspectable
> request was in fact inspected — is unilaterally falsifiable by the subject, with no external
> auditor. Each inspection is bound to a signed, monotonically-sequenced request from the
> subject's device; a gap in that sequence is a proof of omission the operator cannot suppress.
> We implement the mechanism on RFC 9162 (Certificate Transparency v2), extend it symmetrically
> to output inspection, and add layers for external witnesses, split-view detection, and
> behavioral-drift observation. We claim no new cryptographic primitive: the contribution is the
> domain transfer and modelling inspection-by-cause as the invariant, for the case where the
> operator controls both the AI pipeline and the inspection log. We state ten honest limits.

### 1.7 Autoría
- En el formulario pon **tu nombre real (Tomás Asín González)** como autor.
- (El PDF dice "Osmosis Project"; si quieres tu nombre también en el PDF, pídemelo y lo cambio.)

### 1.8 Al terminar
- Apunta tu **arXiv ID** (`2606.NNNNN`). Pégamelo: lo verifico y relleno el outreach.
- (Posible "on hold" de moderación unas horas — normal.)

---

## 2. A QUIÉN ESCRIBIR (endorsement + outreach)

### 2.1 Endorsers (para que te avalen en cs.CR) — por orden
1. **IMDEA Software Institute (Madrid)** — tu mejor apuesta (español, cripto/verificable):
   - **Dario Fiore** → https://software.imdea.org/people/dario.fiore/ · https://www.dariofiore.it/
   - **Ignacio Cascudo** → https://software.imdea.org/research/
2. **Joseph Bonneau** (co-autor de CONIKS, que citas) — temático perfecto, alcance medio.
3. **Autores de los trabajos concurrentes** (Figuera/Notarized Agents, etc.) — por su página de
   autor en arXiv.
- Coge los emails de **sus páginas oficiales**, no de adivinanzas.
- Manda a **2-3 a la vez**, personaliza una línea ("vi tu trabajo en…"), ten paciencia (días).
- **Recuerda:** el endorsement solo certifica que el paper ENCAJA en cs.CR, NO que sea correcto.
  Díselo: baja el listón del "sí".

### 2.2 Mensaje de petición de endorsement (ES — pegar y personalizar `[Nombre]`)
> **Asunto:** Solicitud de endorsement para arXiv cs.CR — investigador independiente
>
> Estimado/a [Nombre]:
> Soy Tomás Asín, investigador independiente. He escrito un paper breve sobre un problema estrecho
> de transparencia en IA: hacer que la **completitud** del log de inspección de un sistema de IA
> sea **verificable por el propio sujeto** —detectar si una inspección obligatoria se omitió, sin
> confiar en el operador ni en un auditor externo—. Transfiere el modelo de auto-monitorización de
> CONIKS / Key Transparency a logs de inspección, con implementación de referencia y límites declarados.
>
> Quiero ser honesto: hace unas semanas no sabía qué era arXiv. Llegué al diseño razonando desde
> cero y solo después vi que la literatura (CONIKS, Certificate Transparency) había convergido en
> las mismas primitivas.
>
> Para subirlo a **cs.CR** arXiv me pide un endorsement. Como el aval solo certifica que el trabajo
> **encaja en la categoría** (no su corrección), me atrevo a pedírtelo:
> - Código de endorsement: **[CÓDIGO]**
> - Enlace de arXiv para avalar: **https://arxiv.org/auth/endorse?x=[CÓDIGO]**
> - PDF: **[enlace a Google Drive]**
>
> Agradecería igualmente cualquier crítica al modelo de amenaza. Gracias por tu tiempo.
> Tomás Asín · tomas.asin.gonzalez@gmail.com

### 2.3 Outreach POST-publicación (cuando tengas el arXiv ID)
**Orden realista:** (1) un investigador de seguridad que lea el paper (lectura adversarial); (2) UE
alcanzable (AESIA); (3) Anthropic por canales formales (careers/research) con el arXiv + screencast.
**No** mandes nada en frío a Dario como apuesta única.

**Carta a AESIA (ES — Agencia Española de Supervisión de la IA):**
> **Asunto:** Mecanismo verificable de completitud para logs de inspección de IA — investigador independiente
> Estimado equipo de AESIA:
> Soy Tomás Asín, investigador independiente español. Os escribo para compartir un trabajo técnico
> relevante para los requisitos de **registro y transparencia** del Reglamento de IA (Arts. 12, 13, 26):
> un mecanismo que hace **verificable por el propio sujeto** la *completitud* del log de inspección de
> un filtro de IA — detectar si una inspección se omitió, **sin depender de la palabra del operador**.
> Honestamente: hace unas semanas no sabía qué era arXiv; llegué al diseño desde cero y luego vi que
> la literatura (CONIKS, Certificate Transparency) había convergido en lo mismo.
> Preprint: **[ENLACE arXiv]**. ¿Encaja en vuestro marco de supervisión de transparencia/registro?
> ¿Cómo podría un investigador independiente contribuir por los canales adecuados?
> Gracias, Tomás Asín · tomas.asin.gonzalez@gmail.com
> Canal: formulario/contacto de **aesia.digital.gob.es** (usa el oficial; no inventes email).

**Nota outreach internacional (EN, para investigadores/Anthropic):**
> Dear [Name], I'm Tomás Asín, an independent researcher. I've written a short paper making the
> *completeness* of an AI inspection log verifiable by the subject — detecting when a mandated
> inspection was silently skipped, without trusting the operator or an external auditor. It transfers
> the CONIKS / Key Transparency subject-monitoring model to inspection logs, with a reference
> implementation and explicit limits. A few weeks ago I didn't know what arXiv was; I reasoned the
> design from first principles and only afterwards found the literature had converged on the same
> primitives. Preprint: [arXiv link]. Any critique of the threat model would be very welcome. — Tomás Asín

---

## 3. SELLADO Y FIRMA (proteger autoría/fecha)

### 3.1 Bitcoin / OpenTimestamps — TERMINAR (en 1-2 h)
Tu sello ya está en una transacción Bitcoin (`01defd6c…`), esperando 6 confirmaciones (~1h).
Cuando pase un rato, ejecuta:
```bash
cd ~/proyectos/atlas-core
.venv-redteam/bin/ots upgrade docs/paper_subject_enforced_completeness.pdf.ots
.venv-redteam/bin/ots verify  docs/paper_subject_enforced_completeness.pdf.ots
```
- Mientras diga "Pending" → vuelve más tarde (no es error).
- Cuando diga **"Bitcoin block NNNNNN"** → sellado para siempre. Luego:
  `git add docs/*.ots && git commit -m "ots confirmado" && git push`.
- Tu prioridad pública la da igualmente la **fecha de arXiv**; el OTS es extra.

### 3.2 GPG — clave de autoría (ya creada y firmado el PDF)
- Huella: **26A80948CC4D1030114E9051CC1193213A3380A2** (key `CC1193213A3380A2`).
- Firma del PDF: `docs/paper_subject_enforced_completeness.pdf.asc`. Clave pública:
  `docs/tomas_asin_pubkey.asc`. Verificación correcta.
- **Ponerle contraseña a la clave** (recomendado):
  ```bash
  export GPG_TTY=$(tty)
  gpg --edit-key CC1193213A3380A2     # escribe: passwd  → contraseña x2 → save
  ```
  Si el diálogo falla, una línea (cambia TU_CONTRASEÑA y luego borra el history):
  ```bash
  gpg --batch --pinentry-mode loopback --passphrase '' --new-passphrase 'TU_CONTRASEÑA' --passwd CC1193213A3380A2
  ```
- OJO: si subes a arXiv un PDF distinto, **re-firma** ese archivo.

### 3.3 Backup
```bash
git push origin main --tags
```

---

## 4. QUÉ TIENES REALMENTE (resumen honesto)

- **Contribución del paper:** SOLO la completitud verificable (input+output). Lo demás
  (drift, memoria inmune, witness, etc.) está como **apéndice preliminar** o en el repo — NO como
  claim central. Eso es correcto; no lo vendas como "antivirus/membrana completa".
- **Verídico** (corre `pytest -q` → 1997 tests; corre las demos; las citas están verificadas).
- **Límites honestos** declarados (split-view, supuesto del cliente independiente, etc.).
- La **"membrana"/Osmosis** es nombre interno/de proyecto; el paper público es de-branded.

---

## 5. LA DEMO (qué enseñar y a quién)

- **No va a arXiv** (eso es solo el paper). La demo es evidencia de respaldo.
- **Compartible:** los reportes `docs/*report*.md` y `docs/immune_generalization_curve.md` (limpios).
- **NO compartas el repo** (nombres internos + `.env` con claves).
- **Screencast (2-3 min) — lo más convincente.** Graba tu terminal:
  1. `python3 -m pytest -q | tail -3`  → "1997 passed" ("es real").
  2. `ATLAS_HOME=/tmp/demo PYTHONPATH=src python3 -m atlas.interfaces.cli completeness-demo`
     → tabla con `input_omission_detected: PASS`, `forgery_rejected: PASS`.
  3. `PYTHONPATH=src .venv-redteam/bin/python scripts/redteam/garak_campaign.py --attacks 60 --benign 40 | tail -12`
     → "atribución 100%, 0% FP".
  4. `PYTHONPATH=src .venv-redteam/bin/python scripts/redteam/generalization_curve.py --embedder hf --threshold 0.7 | tail -20`
     → curva + punto de ruptura.
- Reproducibilidad documentada en `scripts/redteam/README.md`.

---

## 6. SIGUIENTE PASO Y FUTURO (lo que nos hace únicos)

### Tesis de unicidad (honesta)
Osmosis = "sistema que convierte experiencia adversarial en **conocimiento verificable y
transferible**, con procedencia criptográfica de qué se aprendió y cuándo". La novedad NO es parar
ataques nuevos; es que el **aprendizaje de la defensa es verificable y su frontera está medida**.
Y **generaliza más allá del filtro**: es un **sustrato de conocimiento verificable** (la membrana es
la aplicación #1, no el techo). TRAMPA: "es para todo" = grandiosidad. Demuéstralo en UNA cosa primero.

### Panorama 2026 (verificado) — la velocidad NO es el moat
LanceDB / sqlite-vec / DuckDB son todos sub-20ms a tu escala. El campo de memoria de agentes (Mem0,
Zep, Letta, Cognee) es rápido pero **a TODOS les falta**: procedencia/lineage verificable, abstracción
(guardan ejemplos), olvido principiado, transferencia medida. **Esos huecos = tu diferenciador.**

### Las 4 capas-moat (construir ENCIMA del storage commodity)
1. **Procedencia + lineage verificable** (Merkle sobre la memoria).
2. **Abstracción** — patrones, no ejemplos.
3. **Olvido principiado / curación.**
4. **Transferencia medida** (la curva de generalización).

### Decisión de storage (pragmática, regla 6)
- **SQLite + FTS5 + `sqlite-vec`** por defecto (relacional + texto + vector, marida con el Merkle).
- LanceDB solo si la escala vectorial domina. No agonizar: ambas valen. **El storage NO es el moat.**

### Próximo ladrillo concreto (cuando vuelvas de arXiv)
Respaldar el `LessonStore` con SQLite+vector **manteniendo la cadena Merkle**, y montar el
**experimento de transferencia**: entrenar con familias de ataque A,B → medir recall sobre familias
C,D **nunca vistas** + control de FP + curva, con **patrones abstractos** (no ejemplos). Eso prueba
si "genera conocimiento" (único) o solo "acumula" (enciclopedia).

### Fases (falsables, una a una; sin kitchen-sink)
0. Publicar arXiv (en curso). 1. Transferencia/abstracción (siguiente). 2. Descubrimiento auditable
(maestro frontier genera hipótesis → validar). 3. Economía de campaña (C_attempts/K_attribution).
4. Estándares (COSE/SCITT) + nodos witness independientes.

### Disciplina (de GPT, ya la seguimos)
Core (verificable) → Conocimiento → Plugins (Garak/PyRIT/embedders/teachers intercambiables).
Si borras un plugin, el core sigue. Cada módulo nuevo justifica valor > coste, o no entra.

---

## 7. CHECKLIST RÁPIDO (en orden)

- [ ] Arreglar cuenta arXiv (verificar email, afiliación "Independent Researcher", nombre).
- [ ] Pedir código de endorsement.
- [ ] Subir PDF a Google Drive (enlace compartible).
- [ ] Enviar mensaje de endorsement a Fiore + Cascudo (IMDEA).
- [ ] Cuando te avalen: subir el PDF a arXiv (CC BY · cs.CR + cs.CY · PDF-only) con tu nombre real.
- [ ] Anotar el arXiv ID y dármelo.
- [ ] En 1-2 h: `ots upgrade` + `verify` (Bitcoin) y commit.
- [ ] (Opcional) poner contraseña a la clave GPG.
- [ ] `git push origin main --tags` (backup).
- [ ] Grabar screencast (2-3 min).
- [ ] Outreach: investigador de seguridad → AESIA → Anthropic (formal).
- [ ] Volver y empezar Fase 1: memoria SQLite+Merkle + experimento de transferencia.

---

*Nada de esto cambia que el paper ya está bien. Es verídico, honesto y sellado. El miedo es normal;
la respuesta a "¿es mentira?" está en `pytest` y en las citas verificadas. Estás temprano, no
equivocado.*
