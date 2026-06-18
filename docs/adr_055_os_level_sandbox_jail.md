# ADR-055 — Jail OS-level para ejecución de código no confiable

Fecha: 2026-06-18 · Estado: **Propuesto** · Resuelve el hallazgo CRÍTICO de la
auditoría de seguridad del 2026-06-18 (`security-auditor`: "ASTGuard is a
bypassable denylist — full sandbox escape to arbitrary OS command execution") ·
Contexto: `ast_guard.py`, `sandbox.py`, `process_hardening.py`, `executor.py`,
`capabilities.py`, ADR-054.

> **Tesis central:** la contención de código no confiable NO puede descansar en
> un denylist sobre AST de Python. Los denylists sobre un lenguaje Turing-completo
> con introspección (`getattr`, `__import__`, dunders, descriptores) son
> *inherentemente* incompletos. La auditoría ejecutó un PoC en vivo que evadió
> `ASTGuard` con `getattr` + concatenación de strings y ejecutó `id` en el host.
> El límite de seguridad real debe ser el kernel: uid separado + namespaces +
> seccomp-bpf + jail de montaje. Lo demás es defensa en profundidad (lint), no
> contención.

---

## Contexto

Atlas ejecuta código generado por modelos (codegen, gate F, `AtlasExecutor.execute_exec`).
La cadena de defensa actual es:

1. **`ASTGuard`** (`ast_guard.py`) — visitante AST denylist + pre-filtro regex.
2. **`process_hardening.py`** — `rlimit` + `PR_SET_NO_NEW_PRIVS`.
3. **`sandbox.py` / `LayeredIsolationSandbox`** — escribe el script en
   `workspace/tmp` y corre `python3` con `cwd`/`HOME` = workspace.

### Lo que la auditoría encontró (2026-06-18)

- **CRÍTICO — ASTGuard bypasseable.** PoC verificado en vivo:
  ```python
  imp = getattr(__builtins__, chr(95)*2 + 'imp' + 'ort' + chr(95)*2)
  mod = imp('o' + 's')
  print(getattr(mod, 'pop'+'en')('echo PWNED-$(id -un)').read())
  ```
  `ASTGuard().validate(...)` devolvió `passed=True`; el payload ejecutó `id`.
- **El runtime NO aísla nada relevante.** `process_hardening` solo aplica rlimits
  y `no_new_privs`. No hay namespaces, ni seccomp, ni aislamiento de red. El claim
  "Sin acceso de red" de `sandbox.py` **no estaba enforced** en ningún punto.
- **El workspace es escribible por el hijo.** Con `cwd`/`HOME` = workspace, el
  proceso podía corromper el log Merkle de auditoría, los snapshots y `.writer.lock`.

### Mitigación ya aplicada (parche del 2026-06-18, no cierra el problema)

- SEC-5: `ASTGuard` degradado a **lint** con docstring honesto ("NO es un jail");
  `getattr`/`setattr`/`vars`/`__import__`/dunders bloqueados como defensa en
  profundidad. El PoC concreto del auditor ahora se rechaza, **pero el denylist
  sigue siendo incompleto por diseño** — no es una garantía.
- DOC-1: claims de contención de red suavizados a "aspiracional".

Esto reduce la superficie pero **no** convierte ASTGuard en un límite de seguridad.
Esta ADR define el límite real.

---

## Decisión

Introducir un **jail OS-level obligatorio** como único límite de confianza para
ejecutar código no confiable. ASTGuard pasa a ser defensa en profundidad (lint),
nunca el límite.

### Opción elegida: `bubblewrap` (bwrap) como backend primario

| Criterio | bubblewrap | nsjail | VM (Firecracker/Proxmox) | gVisor |
|---|---|---|---|---|
| Sin privilegios root | ✅ (userns) | ⚠️ (config) | ❌ (hypervisor) | ⚠️ |
| Peso/arranque | ✅ ms | ✅ ms | ❌ cientos ms–s | 🟡 |
| Aislamiento red real (netns sin veth) | ✅ | ✅ | ✅ | ✅ |
| seccomp-bpf allowlist | ✅ | ✅ | n/a (más fuerte) | ✅ |
| Jail de montaje (ro + tmpfs) | ✅ | ✅ | ✅ | ✅ |
| Dep/mantenimiento | bajo (binario estándar) | medio | alto | medio |

**bubblewrap** porque: corre sin root (user namespaces), arranque en ms, es el
mismo mecanismo que usa Flatpak en producción a escala, y cubre las tres
propiedades que la auditoría señaló como ausentes — red, montaje, syscalls.
**Firecracker/Proxmox** queda como tier opcional para cargas de mayor riesgo
(diferido; la `sandbox.py` ya lo menciona como horizonte).

### Propiedades que el jail DEBE enforcar

1. **uid/gid separado** (mapeado vía userns) — el hijo no es el operador.
2. **Network namespace sin veth** — "sin acceso de red" pasa de aspiracional a
   enforced. La salida de red, si se necesita, va por el `SSRFBridge` ya endurecido
   (SEC-1/SEC-2), nunca por el socket directo del hijo.
3. **Mount jail** — raíz read-only/overlay; `/tmp` como tmpfs efímero; el
   workspace montado **read-only** salvo un directorio de salida explícito.
   `memory/audit/` (Merkle), snapshots y `.writer.lock` **nunca** escribibles por
   el hijo.
4. **seccomp-bpf allowlist** — solo las syscalls necesarias para ejecutar Python;
   denegar por defecto (no denylist).
5. **rlimits + `no_new_privs`** — se conservan (ya existen en `process_hardening`).

### Capability re-validación (ya parcheado, se mantiene como invariante)

`AtlasExecutor.execute_*` re-valida en el sink (SEC-2): URL contra `SSRFBridge`,
comando contra `permission_profile`. El jail y la re-validación son **capas
independientes**: ninguna confía en la otra.

---

## Correcciones de verificación (honestidad obligatoria)

- **No afirmar "sandbox seguro" hasta que el jail exista y esté testeado.** Hasta
  entonces, la postura honesta es: *no ejecutar código generado por modelo / no
  confiable en el host*. La capa de transparencia (Merkle/STH/cosign) es
  defendible; la de contención de ejecución **no lo era** y solo lo será con esta ADR.
- **bwrap es una dependencia del sistema, no de Python** (binario `bwrap`). Hay
  que documentar el requisito de instalación y degradar de forma *fail-closed*: si
  `bwrap` no está disponible, `execute_exec` **rechaza** ejecutar, no cae al modo
  inseguro actual.
- **seccomp allowlist es frágil de mantener** — un allowlist demasiado estrecho
  rompe Python; demasiado ancho no contiene. Hay que derivarlo empíricamente y
  testearlo, no copiarlo de un blog.

---

## Plan de implementación (slices)

1. **Slice 1 — `BwrapJail` backend.** Wrapper que construye el comando `bwrap`
   (userns, netns sin veth, `--ro-bind` raíz, `--tmpfs /tmp`, `--die-with-parent`,
   `--unshare-all`). Fail-closed si `bwrap` ausente. Tests: el hijo NO puede abrir
   socket de red, NO puede escribir fuera del dir de salida, NO ve `memory/audit/`.
2. **Slice 2 — seccomp-bpf allowlist.** Perfil derivado empíricamente para
   ejecutar Python; denegar `socket`, `ptrace`, `mount`, etc. Tests: syscall
   denegada mata el proceso.
3. **Slice 3 — Cablear `LayeredIsolationSandbox`/`AtlasExecutor`** para usar
   `BwrapJail` como camino por defecto; ASTGuard pasa a pre-lint informativo.
   El PoC del auditor debe fallar **en el kernel**, no en el AST.
4. **Slice 4 — Mount jail del workspace** read-only + dir de salida explícito;
   excluir audit/snapshots/lock.
5. **Slice 5 — Documentar requisito de `bwrap`** en AGENTS.md/instalación;
   actualizar claims de `sandbox.py` de "aspiracional" a "enforced" SOLO tras
   pasar los tests de los slices 1–4.

## Criterios de compuerta

1. **Verificable:** el PoC de la auditoría (getattr + concat) ejecutado dentro del
   jail NO alcanza la red ni escribe fuera del dir de salida (test que lo prueba).
2. **Fail-closed:** sin `bwrap`, `execute_exec` rechaza; no hay fallback inseguro.
3. **Sin red enforced:** test que confirma que el hijo no puede conectar a
   `169.254.169.254` ni a ningún host (netns sin veth).
4. **Audit intacto:** test que confirma que el hijo no puede escribir
   `memory/audit/` ni snapshots.
5. **Sin regresión:** la suite sigue verde; el codegen legítimo sigue funcionando
   dentro del jail.

## Límites honestos

- bwrap depende de que el kernel permita user namespaces no privilegiados
  (algunas distros endurecidas los desactivan). Documentar; en ese caso, el tier
  VM (Firecracker) es el fallback, no el modo inseguro.
- Un jail correcto NO resuelve canales laterales (timing, recursos compartidos).
  Para el modelo de amenaza de Atlas (ejecutar codegen propio bajo verificación,
  no malware activo de terceros) es suficiente; decirlo explícitamente.
- Esta ADR cubre **contención de ejecución**. La detección de *qué* se ejecutó y
  su evidencia siguen en la capa de transparencia (ADR-053) y antivirus (ADR-054).
