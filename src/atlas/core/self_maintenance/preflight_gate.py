"""PreflightGate — el primer paso, más barato y determinista, de autoauditoría.

Antes de gastar ningún LLM en juicio real de una autoauditoría, se descarta
gratis lo obviamente malo: CVEs de dependencias (pip-audit) + radar de
arquitectura/conexión (scripts/sanitation_audit.py). Fail-closed: cualquier
fallo del escaneo de CVEs (no del hallazgo de vulnerabilidades en sí, sino de
la ejecución del escaneo) se trata como "no pasa" — nunca se asume "sin CVEs"
por defecto ante una duda.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]

#: Caracteres tras el nombre del venv en los que buscar `bin` para distinguir
#: "lo lanza" de "lo nombra". `_REPO_ROOT / ".venv-scraping" / "bin" / "python3"`
#: deja ~20; se da holgura sin llegar a la línea siguiente.
_VENTANA_LANZAMIENTO = 60


@dataclass
class PreflightResult:
    passed: bool
    cve_found: bool
    cve_findings: list[str]
    sanitation_findings: dict[str, list[str]]
    #: CVEs de venvs aislados que hoy no invoca ningún camino de runtime.
    #: Se informan y NO bloquean — ver `PreflightGate._scan_cves`.
    cve_advisories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "cve_found": self.cve_found,
            "cve_findings": list(self.cve_findings),
            "cve_advisories": list(self.cve_advisories),
            "sanitation_findings": dict(self.sanitation_findings),
        }


class PreflightGate:
    def __init__(
        self,
        *,
        python_executable: str | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._python = python_executable or sys.executable
        self._root = Path(repo_root) if repo_root is not None else _REPO_ROOT
        self._cache_lanzados: frozenset[str] | None = None

    def check(self) -> PreflightResult:
        cve_found, cve_findings, cve_advisories = self._scan_cves()
        sanitation_findings = self._run_sanitation()
        return PreflightResult(
            passed=not cve_found,
            cve_found=cve_found,
            cve_findings=cve_findings,
            cve_advisories=cve_advisories,
            sanitation_findings=sanitation_findings,
        )

    def _isolated_venvs(self) -> list[Path]:
        """Los venvs hermanos del repo, DESCUBIERTOS y no listados a mano.

        Una lista de nombres se queda vieja en cuanto alguien añade un venv, y
        ése es exactamente el fallo que esto arregla: los tres aislados
        (`.venv-scraping`, `.venv-desktop`, `.venv-redteam`) llevaban desde que
        existen sin que nadie les pasara pip-audit.
        """
        # `sys.prefix`, no `Path(sys.executable).resolve()`: en un venv el
        # `bin/python` es un SYMLINK al intérprete del sistema, así que
        # resolverlo devuelve /usr y el propio venv se colaba en su propia
        # lista de "aislados" (visto al ejecutarlo, no al leerlo).
        propio = Path(sys.prefix).resolve()
        return sorted(
            p for p in self._root.glob(".venv*")
            if p.is_dir() and (p / "bin" / "python").exists()
            and p.resolve() != propio
        )

    def _venv_en_ruta_de_runtime(self, venv: Path) -> bool:
        """¿Lo LANZA algún módulo de `src/`?

        Criterio comprobable en vez de una lista de opinión, pero el criterio
        obvio —"aparece su nombre"— da falso positivo en los tres: los venvs se
        mencionan en listas de exclusión de barrido (`tool_coder`,
        `dormant_modules`) y en mensajes de error ("pendiente de un entorno con
        Xvfb :99 + .venv-desktop"), y mencionar no es invocar. Con ese criterio
        los tres bloqueaban y la puerta se volvía inservible.

        Lo que distingue una invocación real es que el nombre aparezca junto a
        la construcción del intérprete: `crawler.py` hace
        `_REPO_ROOT / ".venv-scraping" / "bin" / "python3"`. Se busca `bin`
        dentro de la misma vecindad textual, que es lo que separa lanzarlo de
        nombrarlo. El criterio se actualiza solo el día que alguien cablee uno.
        """
        return venv.name in self._lanzados()

    def _lanzados(self) -> frozenset[str]:
        """Nombres de venv que `src/` lanza. Una sola pasada, cacheada.

        Preguntarlo venv a venv releía los 359 ficheros de `src/` por cada uno
        —y `check()` se llama en cada preflight—: mismo resultado, tres veces el
        trabajo. Se recorre una vez y se responde a todos.
        """
        if self._cache_lanzados is not None:
            return self._cache_lanzados
        nombres = [p.name for p in self._isolated_venvs()]
        encontrados: set[str] = set()
        src = self._root / "src"
        if src.is_dir() and nombres:
            for py in src.rglob("*.py"):
                if len(encontrados) == len(nombres):
                    break
                try:
                    texto = py.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for nombre in nombres:
                    if nombre in encontrados:
                        continue
                    desde = 0
                    while (i := texto.find(nombre, desde)) != -1:
                        desde = i + 1
                        if "bin" in texto[i : i + len(nombre) + _VENTANA_LANZAMIENTO]:
                            encontrados.add(nombre)
                            break
        self._cache_lanzados = frozenset(encontrados)
        return self._cache_lanzados

    def _scan_cves(self) -> tuple[bool, list[str], list[str]]:
        """CVEs del venv principal + de cada venv aislado del repo.

        Los del principal y los de un venv aislado QUE EL RUNTIME INVOCA
        bloquean. Los de un venv que hoy no invoca nadie se informan aparte:
        tumbar el lazo entero por una CVE inalcanzable es el fail-closed sobre
        falso positivo que ya se pagó esta semana, y callarla es lo contrario.
        """
        bloqueantes: list[str] = []
        avisos: list[str] = []
        fallo, hallazgos = self._audit_target(None)
        bloqueantes.extend(hallazgos)
        for venv in self._isolated_venvs():
            sub_fallo, sub = self._audit_target(venv)
            etiquetados = [f"{venv.name} {h}" for h in sub]
            if self._venv_en_ruta_de_runtime(venv):
                fallo = fallo or sub_fallo
                bloqueantes.extend(etiquetados)
            else:
                avisos.extend(etiquetados)
        return fallo, bloqueantes, avisos

    def _audit_target(self, venv: Path | None) -> tuple[bool, list[str]]:
        cmd = [self._python, "-m", "pip_audit", "--format", "json"]
        if venv is not None:
            sitios = sorted(venv.glob("lib/python*/site-packages"))
            if not sitios:
                return True, [f"{venv.name}: sin site-packages legible"]
            cmd += ["--path", str(sitios[-1])]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return True, [f"pip-audit no pudo ejecutarse: {exc}"]
        # pip-audit devuelve returncode!=0 cuando SÍ encuentra vulnerabilidades
        # (ese es el comportamiento esperado, no un fallo del escaneo) — no
        # tratar returncode!=0 como fallo de ejecución; solo un stdout no-JSON
        # o una excepción real cuentan como "el escaneo no corrió".
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            return True, [f"pip-audit no pudo ejecutarse: salida no-JSON ({exc}); stderr: {result.stderr[:300]}"]
        findings: list[str] = []
        for dep in data.get("dependencies", []):
            for vuln in dep.get("vulns", []) or []:
                fixes = ",".join(vuln.get("fix_versions", []) or []) or "sin fix conocido"
                findings.append(
                    f"{dep.get('name')}=={dep.get('version')}: {vuln.get('id')} (fix: {fixes})"
                )
        return bool(findings), findings

    def _run_sanitation(self) -> dict[str, list[str]]:
        try:
            spec = importlib.util.spec_from_file_location(
                "sanitation_audit", _REPO_ROOT / "scripts" / "sanitation_audit.py"
            )
            if spec is None or spec.loader is None:
                raise ImportError("no se pudo cargar scripts/sanitation_audit.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return {
                "vapor": module.vapor_audit(),
                "classified_zero_importers": module.classified_zero_importers(),
                "graveyard_overdue": module.graveyard_overdue(),
                "empty_dirs": module.empty_dirs(),
                "stale_refs": module.stale_refs(),
                # 2026-07-08 (orden real de docs): desviaciones árbol↔INDEX.yaml
                # y del grafo de enlaces entran en el preflight del lazo — el
                # orden se defiende solo.
                "docs_index_drift": module.docs_index_drift(),
                "docs_graph_drift": module.docs_graph_drift(),
                "ecosystem_map_drift": module.ecosystem_map_drift(),
                # 2026-07-30: la deriva canon↔grafo AST pertenece a ESTA
                # puerta y no sólo al radar manual. Es la que gobierna la
                # automodificación: el lazo no debería proponerse cambios
                # mientras `component_reality_matrix.jsonl` miente sobre qué
                # está cableado, porque ese mismo canon es lo que un driver
                # nuevo lee para decidir dónde tocar.
                "component_wiring_drift": module.component_wiring_drift(),
            }
        except Exception as exc:  # noqa: BLE001 — radar opcional, nunca bloquea
            return {"error": [f"sanitation_audit no pudo ejecutarse: {exc}"]}
