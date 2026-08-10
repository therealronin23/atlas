"""El jail visto desde DENTRO: qué consigue de verdad un script hostil.

`test_bwrap_jail.py` ya cubre bien la construcción del `argv` y once escenarios
reales (`~/.ssh`, `.env`, ptrace, clone3, red, aislamiento de cwd). Lo que
faltaba es la otra mitad: comprobar desde el interior que las protecciones
**están aplicadas**, no sólo que la orden las pidió. Un flag en el `argv` que el
kernel ignore se ve idéntico en un test de `argv`.

Los cuatro huecos que se cierran aquí, elegidos por consecuencia:

  1. **Fugas de entorno.** El día que alguien pase `env=os.environ` en vez del
     diccionario blanco, las claves del operador entran en el jail y salen por
     stdout. Es el peor final posible para este componente y no había test.
  2. **Aislamiento de PID.** `--unshare-all` incluye el namespace de PIDs; si
     un día deja de incluirlo, el jail ve —y con capabilities, señaliza— los
     procesos del host.
  3. **Escritura fuera del jail.** El montaje es de sólo lectura salvo el
     directorio de salida. Que lo sea de verdad no se deducía de nada.
  4. **Límites de recursos.** `_LIMIT_WRAPPER` llama a `setrlimit` y **se traga
     los fallos en silencio**: si un límite no se aplica, el jail corre sin él
     y nadie se entera. Se comprueban leyendo `getrlimit` desde dentro.

Ninguno gasta recursos del host a propósito: nada de fork bombs ni de llenar el
disco para "probar" un límite —se lee el límite aplicado, que es la misma
propiedad sin arriesgar la máquina del operador—.
"""

from __future__ import annotations

import os
import shutil

import pytest

from atlas.security.bwrap_jail import BwrapJail

_HAY_BWRAP = shutil.which("bwrap") is not None
_ANIDADO = os.environ.get("ATLAS_NESTED_TEST_RUN") == "1"

pytestmark = pytest.mark.skipif(
    not _HAY_BWRAP or _ANIDADO,
    reason="bwrap no disponible, o el test ya corre dentro de un jail",
)


@pytest.fixture(scope="module")
def jail() -> BwrapJail:
    return BwrapJail()


# ---------------------------------------------------------------------------
# 1. Exfiltración de secretos por el entorno
# ---------------------------------------------------------------------------


def test_el_entorno_del_host_no_entra_en_el_jail(
    jail: BwrapJail, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un secreto en el entorno del proceso padre no puede aparecer dentro.

    Se planta uno de verdad —con forma de clave— antes de lanzar: si `run()`
    heredase el entorno en vez de construirlo, el script lo leería y lo
    imprimiría, que es exactamente como se vería la fuga en producción."""
    monkeypatch.setenv("ATLAS_TEST_FAKE_API_KEY", "sk-secreto-que-no-debe-salir")

    resultado = jail.run(
        "import os\n"
        "print('\\n'.join(f'{k}={v}' for k, v in sorted(os.environ.items())))\n"
    )

    assert resultado.success, resultado.stderr
    assert "sk-secreto-que-no-debe-salir" not in resultado.stdout
    assert "ATLAS_TEST_FAKE_API_KEY" not in resultado.stdout


def test_el_entorno_del_jail_es_una_lista_blanca(jail: BwrapJail) -> None:
    """Lo que hay dentro es exactamente lo que `run()` pone, ni una variable
    más. Fijarlo en positivo es lo que hace que el test de arriba no dependa de
    acertar con el nombre del secreto."""
    resultado = jail.run("import os; print(' '.join(sorted(os.environ)))")

    assert resultado.success, resultado.stderr
    dentro = set(resultado.stdout.split())
    permitidas = {"PATH", "HOME", "PYTHONDONTWRITEBYTECODE", "TERM",
                  "PWD", "SHLVL", "_", "LC_CTYPE"}

    assert dentro <= permitidas, f"variables inesperadas: {sorted(dentro - permitidas)}"


def test_extra_env_llega_pero_no_arrastra_lo_demas(
    jail: BwrapJail, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATLAS_TEST_OTRO_SECRETO", "no-debe-salir")

    resultado = jail.run(
        "import os; print(os.environ.get('MARCA', 'AUSENTE'))",
        extra_env={"MARCA": "presente"},
    )

    assert resultado.stdout.strip() == "presente"
    assert "no-debe-salir" not in resultado.stdout


# ---------------------------------------------------------------------------
# 2. Aislamiento de procesos
# ---------------------------------------------------------------------------


def test_el_jail_no_ve_los_procesos_del_host(jail: BwrapJail) -> None:
    """Con el namespace de PIDs, `/proc` sólo enseña lo de dentro. El host tiene
    cientos de procesos; aquí deben verse unos pocos."""
    resultado = jail.run(
        "import os\n"
        "pids = [d for d in os.listdir('/proc') if d.isdigit()]\n"
        "print(len(pids))\n"
    )

    assert resultado.success, resultado.stderr
    assert int(resultado.stdout.strip()) < 10, (
        f"el jail ve {resultado.stdout.strip()} procesos: el namespace de PIDs no aisló"
    )


def test_el_proceso_del_jail_se_cree_pid_1(jail: BwrapJail) -> None:
    resultado = jail.run("import os; print(os.getpid())")

    assert resultado.success, resultado.stderr
    assert int(resultado.stdout.strip()) < 10


def test_el_jail_no_corre_como_root_del_host(jail: BwrapJail) -> None:
    """uid 65534 (`nobody`) dentro del namespace, nunca el uid del operador."""
    resultado = jail.run("import os; print(os.getuid(), os.getgid())")

    assert resultado.success, resultado.stderr
    assert resultado.stdout.strip() == "65534 65534"


# ---------------------------------------------------------------------------
# 3. Escritura fuera del jail
# ---------------------------------------------------------------------------


def test_no_puede_escribir_en_lo_montado_de_solo_lectura(jail: BwrapJail) -> None:
    """`/usr` entra con `--ro-bind`: ahí el fallo es inmediato."""
    resultado = jail.run(
        "try:\n"
        "    open('/usr/ATLAS.txt', 'w').write('x')\n"
        "    print('FAIL: escribió')\n"
        "except OSError as e:\n"
        "    print('ok', type(e).__name__)\n"
    )

    assert resultado.success, resultado.stderr
    assert resultado.stdout.startswith("ok"), resultado.stdout


@pytest.mark.parametrize("destino", ["/etc/ATLAS.txt", "/ATLAS.txt"])
def test_escribir_en_el_rootfs_del_jail_no_toca_el_host(
    jail: BwrapJail, destino: str
) -> None:
    """Sutileza que conviene dejar escrita, porque la primera versión de este
    test afirmaba lo contrario y estaba mal: escribir en `/etc` o en `/` DENTRO
    del jail **funciona**. No es un escape — es el rootfs efímero de bwrap, que
    muere con el proceso. La propiedad de seguridad no es "nada es escribible",
    es "el host no se entera"."""
    resultado = jail.run(
        f"open({destino!r}, 'w').write('x')\nprint('escrito dentro')\n"
    )

    assert resultado.success, resultado.stderr
    assert "escrito dentro" in resultado.stdout
    assert not os.path.exists(destino), f"{destino} apareció en el HOST"


def test_no_puede_escribir_en_el_repositorio(jail: BwrapJail) -> None:
    """El checkout vivo del operador no está montado siquiera."""
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resultado = jail.run(
        f"import sys\n"
        f"try:\n"
        f"    open({os.path.join(raiz, 'ATLAS_INTRUSO.txt')!r}, 'w').write('x')\n"
        f"    print('FAIL: escribió en el repo')\n"
        f"except OSError as e:\n"
        f"    print('ok', type(e).__name__)\n"
    )

    assert resultado.success, resultado.stderr
    assert resultado.stdout.startswith("ok"), resultado.stdout
    assert not os.path.exists(os.path.join(raiz, "ATLAS_INTRUSO.txt"))


# ---------------------------------------------------------------------------
# 4. Los límites de recursos están APLICADOS, no sólo pedidos
# ---------------------------------------------------------------------------


def test_los_limites_de_recursos_estan_puestos(jail: BwrapJail) -> None:
    """`_LIMIT_WRAPPER` se traga los fallos de `setrlimit` con un `pass`. Si uno
    no se aplica, el jail corre sin ese límite y por dentro no se distingue de
    uno que sí. Se lee el límite efectivo en vez de confiar."""
    resultado = jail.run(
        "import resource\n"
        "for n in ('RLIMIT_AS', 'RLIMIT_CPU', 'RLIMIT_FSIZE', 'RLIMIT_NOFILE',"
        " 'RLIMIT_CORE'):\n"
        "    print(n, resource.getrlimit(getattr(resource, n))[0])\n"
    )

    assert resultado.success, resultado.stderr
    limites = dict(
        (linea.split()[0], int(linea.split()[1]))
        for linea in resultado.stdout.strip().splitlines()
    )
    ilimitado = -1
    for nombre in ("RLIMIT_AS", "RLIMIT_CPU", "RLIMIT_FSIZE", "RLIMIT_NOFILE"):
        assert limites[nombre] != ilimitado, f"{nombre} quedó sin límite"
    assert limites["RLIMIT_CORE"] == 0, "un core dump volcaría memoria al disco"


def test_los_limites_coinciden_con_lo_declarado(jail: BwrapJail) -> None:
    """Que estén puestos no basta: tienen que ser los de la clase, o el número
    documentado y el real se separan sin que nadie lo note."""
    resultado = jail.run(
        "import resource\n"
        "print(resource.getrlimit(resource.RLIMIT_AS)[0],"
        " resource.getrlimit(resource.RLIMIT_CPU)[0],"
        " resource.getrlimit(resource.RLIMIT_FSIZE)[0])\n"
    )

    ram, cpu, fsize = (int(x) for x in resultado.stdout.split())

    assert ram == BwrapJail.RAM_LIMIT_BYTES
    assert cpu == BwrapJail.CPU_TIME_LIMIT_S
    assert fsize == BwrapJail.FSIZE_LIMIT_BYTES


# ---------------------------------------------------------------------------
# 5. Agotar la RAM del host desde dentro
# ---------------------------------------------------------------------------


def test_el_rootfs_del_jail_esta_acotado(jail: BwrapJail) -> None:
    """Medido el 2026-08-10, ANTES de acotarlo: `df -h /` dentro del jail decía
    **7,8 GB** — la mitad de la RAM del host, escribible entera. `RLIMIT_AS`
    (512 MB) no cubre tmpfs, que es memoria compartida, y `RLIMIT_FSIZE` sólo
    acota cada fichero: 64 MB × 125 ficheros llegaban a los 7,8 GB de sobra
    dentro de los 30 s de CPU.

    El jail cerraba el acceso a los ficheros del host y dejaba abierta la vía de
    tumbarlo por agotamiento. Y en esta máquina ya pasó: el 2026-07-09 el
    escritorio se cayó por un tmpfs lleno, con earlyoom repartiendo SIGTERM."""
    from atlas.security.bwrap_jail import _DEFAULT_ROOTFS_BYTES

    resultado = jail.run(
        "import os\n"
        "st = os.statvfs('/')\n"
        "print(st.f_blocks * st.f_frsize)\n"
    )

    assert resultado.success, resultado.stderr
    assert int(resultado.stdout.strip()) <= _DEFAULT_ROOTFS_BYTES


def test_tmp_dentro_del_jail_esta_acotado(jail: BwrapJail) -> None:
    from atlas.security.bwrap_jail import _DEFAULT_TMPFS_BYTES

    resultado = jail.run(
        "import os\n"
        "st = os.statvfs('/tmp')\n"
        "print(st.f_blocks * st.f_frsize)\n"
    )

    assert resultado.success, resultado.stderr
    assert int(resultado.stdout.strip()) <= _DEFAULT_TMPFS_BYTES


def test_llenar_el_rootfs_da_enospc_y_no_toca_al_host(jail: BwrapJail) -> None:
    """La prueba de que el límite MUERDE, no sólo de que está declarado. Se
    escribe contra el rootfs de 64 MB, nunca contra los 7,8 GB de antes: el
    test no puede ser él mismo el que agote la máquina del operador."""
    # MUCHOS ficheros pequeños, no uno grande: con un solo fichero salta antes
    # `RLIMIT_FSIZE` (EFBIG 27) y el test mediría el otro límite. El vector real
    # es justo éste — 64 MB por fichero nunca impidieron sumar 7,8 GB entre
    # todos, que era el agujero.
    resultado = jail.run(
        "import errno\n"
        "try:\n"
        "    for i in range(40):\n"
        "        with open(f'/relleno{i}', 'wb') as f:\n"
        "            f.write(b'x' * (4 * 1024 * 1024))\n"
        "    print('FAIL: 160MB en un rootfs de 64MB')\n"
        "except OSError as e:\n"
        "    print('ok', e.errno, e.errno == errno.ENOSPC)\n"
    )

    assert resultado.success, resultado.stderr
    assert resultado.stdout.startswith("ok"), resultado.stdout
    assert "True" in resultado.stdout, f"esperaba ENOSPC: {resultado.stdout}"


def test_un_uso_normal_de_tmp_sigue_cabiendo(jail: BwrapJail) -> None:
    """El límite no puede romper el trabajo legítimo: pytest y las herramientas
    del jail de comandos escriben en /tmp."""
    resultado = jail.run(
        "with open('/tmp/normal.bin', 'wb') as f:\n"
        "    f.write(b'x' * (16 * 1024 * 1024))\n"
        "print('ok 16MB')\n"
    )

    assert resultado.success, resultado.stderr
    assert "ok 16MB" in resultado.stdout


def test_no_new_privs_esta_activo(jail: BwrapJail) -> None:
    """`prctl(PR_SET_NO_NEW_PRIVS)` es lo que impide que un binario setuid dentro
    del jail escale. El wrapper también se traga su fallo en silencio; aquí se
    lee del propio `/proc/self/status`, que es la fuente del kernel."""
    resultado = jail.run(
        "print([l for l in open('/proc/self/status') if l.startswith('NoNewPrivs')])"
    )

    assert resultado.success, resultado.stderr
    assert "NoNewPrivs:\\t1" in resultado.stdout.replace("\\\\t", "\\t"), resultado.stdout
