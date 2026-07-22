"""A3.1 — Materializador explícito de fuentes LOCALES a staging inmutable.

ADR-073 (consecuencias A3) y docs/design/plugin_manifest_v1.md (condiciones
A3.1-2): materializa a un directorio NUEVO bajo el staging root, fija
contenido y procedencia (hash de árbol medido antes Y después de copiar),
y re-escanea vía `PluginAdmissionGate` DESPUÉS de materializar — la admisión
queda ligada a los bytes staged, no a los de la fuente.

Fronteras deliberadas de esta loncha:

- Solo fuentes locales. Un fetcher remoto (git/http) es red implícita y
  exige su propio escrutinio en un ADR posterior — aquí ni existe.
- Sin hooks, sin red, sin procesos: por construcción (este módulo no importa
  subprocess/socket/urllib; hay un test que lo fija) — no por promesa.
- La procedencia va en un sidecar `<dest>.provenance.json` FUERA del árbol
  staged: los bytes que escaneó el gate son exactamente los admitidos.
- La copia escribe solo bytes de ficheros regulares (nada de symlinks,
  permisos ni bits de ejecución: un plugin declarativo no tiene ejecutables).
- Materializar NUNCA otorga activación: el veredicto del gate se devuelve
  tal cual (admit/review/block) y un block no borra el árbol — la revocación
  y limpieza de staging pertenecen al activador A3.3/operador.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from atlas.mcp.plugin_admission import PluginAdmission, PluginAdmissionGate
from atlas.security.supply_chain import ScanLimits
from atlas.security.supply_chain_models import IndicatorCatalog

_SAFE_NAME = re.compile(r"[^a-z0-9-]+")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaterializedProvenance(_StrictModel):
    """Procedencia MEDIDA por el materializador (no asertada por la fuente)."""

    schema_version: Literal["1.0"]
    source_kind: Literal["local"]
    origin: str
    revision: str
    tree_sha256: str
    file_count: int
    total_bytes: int
    materialized_at: str


class MaterializationResult(_StrictModel):
    schema_version: Literal["1.0"]
    status: Literal["materialized", "failed"]
    staged_root: str | None
    provenance: MaterializedProvenance | None
    admission: PluginAdmission | None
    reason_codes: list[str]


class PluginMaterializer:
    """Copia un árbol local a staging de forma fail-closed y lo re-escanea."""

    def __init__(
        self,
        *,
        staging_root: Path,
        gate: PluginAdmissionGate | None = None,
        limits: ScanLimits | None = None,
    ) -> None:
        self._staging_root = staging_root.absolute()
        self._gate = gate or PluginAdmissionGate(staging_root=staging_root)
        self._limits = limits or ScanLimits()

    def materialize_local(
        self,
        source: Path,
        *,
        expected_plugin_id: str | None = None,
        catalog: IndicatorCatalog | None = None,
    ) -> MaterializationResult:
        source_path = source.absolute()
        veto = self._veto_source(source_path)
        if veto is not None:
            return _failed(veto)

        walked = self._walk_source(source_path)
        if isinstance(walked, str):
            return _failed(walked)
        files, total_bytes = walked
        tree_sha256 = _tree_sha256(files)

        dest = self._staging_root / f"{_safe_name(source_path.name)}-{tree_sha256[:12]}"
        sidecar = dest.with_name(dest.name + ".provenance.json")
        if dest.exists() or sidecar.exists():
            return _failed("destination_exists")

        copy_error = self._copy(source_path, dest, files)
        if copy_error is not None:
            # Artefacto parcial NUESTRO, jamás escaneado ni admitido: se borra.
            shutil.rmtree(dest, ignore_errors=True)
            return _failed(copy_error)

        staged_files = self._walk_source(dest)
        if isinstance(staged_files, str) or _tree_sha256(staged_files[0]) != tree_sha256:
            shutil.rmtree(dest, ignore_errors=True)
            return _failed("staging_mutation_detected")

        provenance = MaterializedProvenance(
            schema_version="1.0",
            source_kind="local",
            origin=f"local://{source_path}",
            revision=f"sha256:{tree_sha256}",
            tree_sha256=tree_sha256,
            file_count=len(files),
            total_bytes=total_bytes,
            materialized_at=datetime.now(timezone.utc).isoformat(),
        )
        sidecar.write_text(provenance.model_dump_json(indent=2), encoding="utf-8")

        admission = self._gate.admit(
            dest, expected_plugin_id=expected_plugin_id, catalog=catalog
        )
        return MaterializationResult(
            schema_version="1.0",
            status="materialized",
            staged_root=str(dest),
            provenance=provenance,
            admission=admission,
            reason_codes=[],
        )

    def _veto_source(self, source: Path) -> str | None:
        if source.is_symlink() or not source.is_dir():
            return "source_not_a_directory"
        if source.resolve(strict=False) != source:
            return "source_not_canonical"
        try:
            self._staging_root.mkdir(parents=True, exist_ok=True)
        except OSError:
            return "staging_root_unavailable"
        if self._staging_root.is_symlink():
            return "staging_root_symlink"
        staging = self._staging_root.resolve(strict=False)
        if source == staging or staging in source.parents or source in staging.parents:
            return "source_overlaps_staging"
        return None

    def _walk_source(
        self, root: Path
    ) -> tuple[list[tuple[str, str, int]], int] | str:
        """(relpath_posix, sha256, size) por fichero, o un reason code."""

        files: list[tuple[str, str, int]] = []
        total = 0
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                return "source_symlink"
            if path.is_dir():
                continue
            if not path.is_file():
                return "source_irregular_file"
            size = path.stat().st_size
            if size > self._limits.max_file_bytes:
                return "source_file_too_large"
            total += size
            if total > self._limits.max_total_bytes:
                return "source_too_large"
            if len(files) >= self._limits.max_files:
                return "source_too_many_files"
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            files.append((path.relative_to(root).as_posix(), digest, size))
        return files, total

    def _copy(
        self, source: Path, dest: Path, files: list[tuple[str, str, int]]
    ) -> str | None:
        try:
            dest.mkdir(parents=True, exist_ok=False)
            for relative, expected_sha256, _size in files:
                data = (source / relative).read_bytes()
                if hashlib.sha256(data).hexdigest() != expected_sha256:
                    return "source_changed_during_copy"
                target = dest / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        except OSError:
            return "copy_failed"
        return None


def _tree_sha256(files: list[tuple[str, str, int]]) -> str:
    entries = [f"{relative}\0{digest}" for relative, digest, _size in sorted(files)]
    return hashlib.sha256("\n".join(entries).encode("utf-8")).hexdigest()


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME.sub("-", name.lower()).strip("-")
    return cleaned or "plugin"


def _failed(code: str) -> MaterializationResult:
    return MaterializationResult(
        schema_version="1.0",
        status="failed",
        staged_root=None,
        provenance=None,
        admission=None,
        reason_codes=[code],
    )
