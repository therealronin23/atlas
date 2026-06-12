# ADR-034 — Endurecimiento del subprocess de ejecución (Post-F hardening)

- Status: **Accepted** (2026-05-30)
- Módulos: `src/atlas/security/process_hardening.py` (nuevo),
  `src/atlas/security/sandbox.py`
- Depende de: Gate F (tools mutantes de host), `LayeredIsolationSandbox`

## Contexto

`LayeredIsolationSandbox._execute_normal` ya ejecuta código no confiable en un
subprocess con tres límites POSIX (`RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_CORE=0`),
timeout wall-clock y un entorno mínimo (`_safe_env`). Es la base correcta, pero
deja agujeros que el roadmap anotó como **"eBPF / seccomp hardening (Post-F)"**:

1. **Escalada de privilegios**: sin `PR_SET_NO_NEW_PRIVS`, un binario setuid
   invocado por el hijo puede ganar privilegios. Es la mitigación más barata y
   de mayor impacto.
2. **Fork bomb**: sin `RLIMIT_NPROC`, el hijo puede agotar la tabla de procesos.
3. **Llenado de disco**: sin `RLIMIT_FSIZE`, el hijo puede escribir un archivo
   arbitrariamente grande hasta llenar el FS.
4. **Agotamiento de descriptores**: sin `RLIMIT_NOFILE`, puede abrir fds sin
   tope.
5. **Procesos huérfanos**: sin sesión propia, matar el sandbox por timeout deja
   hijos vivos.

El roadmap menciona "eBPF / seccomp", pero el filtrado de syscalls real exige
`libseccomp`/`pyseccomp` (dependencia nueva → choca con la regla 6) y validación
con kernel/eBPF tooling que no se puede testear en local sin hardware dedicado.

## Decisión

Implementar el endurecimiento **factible y stdlib-only ahora**, y dejar el
filtrado de syscalls como punto de extensión documentado.

| # | Tema | Elección | Razón |
|---|------|----------|-------|
| 1 | No-new-privs | `prctl(PR_SET_NO_NEW_PRIVS, 1)` vía `ctypes` contra libc | Stdlib (ctypes); corta la escalada por setuid. Irreversible y heredado por hijos: exactamente lo que queremos |
| 2 | Límites extra | Añadir `RLIMIT_NPROC`, `RLIMIT_FSIZE`, `RLIMIT_NOFILE` a los 3 existentes | Cierra fork bomb, disk fill y fd exhaustion con una llamada cada uno |
| 3 | Aislamiento de sesión | `subprocess.run(start_new_session=True)` (= `setsid` en el hijo) | El timeout puede matar todo el grupo; no deja huérfanos. Más limpio que `os.setsid` manual en preexec |
| 4 | Dónde vive | Módulo nuevo `process_hardening.py` con funciones puras (`default_rlimits`) + aplicador (`apply_in_child`) | Testeable sin forkear; reusable por cualquier ejecutor futuro, no solo el sandbox |
| 5 | Tolerancia a fallo | Cada límite y el prctl van en su propio try/except; el preexec **nunca** lanza | Si lanzara, el hijo muere antes del exec. Mejor degradar a "menos hardening" que romper |
| 6 | seccomp/eBPF | Fuera de alcance; punto de extensión anotado (`apply_in_child` es el hook) | Regla 6 (sin deps nuevas) + no validable en local |
| 7 | Deps | Ninguna nueva (ctypes, resource, subprocess: stdlib) | Regla 6 |
| 8 | Perfil para procesos de larga vida (2026-06-12) | `default_rlimits` acepta `ram_bytes/cpu_seconds/nproc = None` para omitir `RLIMIT_AS`/`RLIMIT_CPU`/`RLIMIT_NPROC`; el transport MCP los pasa `None` | Esos tres caps están calibrados para snippets efímeros y son **mortales** para runtimes persistentes multihilo: `AS` limita VIRTUAL (node/V8/Rust reservan gigas), `CPU` es ACUMULADA (un server la agota → SIGKILL), `NPROC` es POR-USUARIO (EAGAIN con miles de hilos vivos). Confirmado contra 3 servers reales en la primera adopción autónoma |
| 9 | Control compensatorio | `MemoryMax=4G`/`TasksMax=4096` en el unit systemd de atlas-core | El bound de recursos correcto para procesos persistentes es el cgroup del servicio, no un `RLIMIT_*` por-proceso: acota TODO el árbol (incluidos servers MCP adoptados) sin romper runtimes. La seguridad de adopción MCP vive en Sentinel + decisor (qué se adopta), no en el cap de recursos |

## Compatibilidad

- `_safe_env`, AST Guard, timeout y los 3 rlimits previos: intactos.
- En plataformas sin `prctl`/rlimits aplicables (no-Linux), cada paso degrada a
  no-op silencioso; el subprocess sigue corriendo. Comportamiento previo
  preservado.

## Consecuencias

- El subprocess de ejecución pasa de "limitado en CPU/RAM" a "limitado en
  CPU/RAM/procesos/tamaño de archivo/fds + sin escalada de privilegios + sesión
  aislada".
- `process_hardening.py` queda como única fuente de verdad del endurecimiento de
  procesos, reusable por ColdUpdate apply, validation_runner, etc.

## Fuera de alcance

- Filtrado de syscalls (seccomp-bpf) — exige dep nueva; hook dejado.
- Namespaces (mount/net/pid) vía `unshare` — requiere privilegios o userns;
  evaluación futura.
- OMEGA tier real (Proxmox + snapshot) — sigue stub, ADR-002.

## Tests

`tests/test_process_hardening.py`:
- `test_default_rlimits_includes_hardening_limits`
- `test_set_no_new_privs_in_subprocess` (aplicado en subproceso para no
  contaminar el proceso de pytest)
- `test_sandbox_enforces_fsize_limit` (E2E: escribir > FSIZE → proceso muere)
- `test_sandbox_runs_in_new_session` (E2E: el hijo es líder de su sesión)
- `test_hardening_never_raises_on_exotic_platform`
