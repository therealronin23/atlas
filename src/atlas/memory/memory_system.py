"""
Atlas Core — Sistema de Memoria
SystemContextLoader, ErrorRegistry, ApprovedPatternStore, ProviderMetricsStore, ToolRegistry.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atlas.core.contracts import Tool, ToolLevel, PermissionLevel


# ===========================================================================
# SystemContextLoader — Contexto permanente de sistema
# ===========================================================================

@dataclass
class SystemContextLoader:
    """
    Contexto permanente que Atlas siempre tiene cargado.
    01_vision.md, 02_rules.md, 03_adr.md
    """
    vision: str    = ""
    rules: str     = ""
    adr: str       = ""

    @classmethod
    def load(cls, base_path: Path) -> "SystemContextLoader":
        def read(name: str) -> str:
            p = base_path / name
            return p.read_text(encoding="utf-8") if p.exists() else ""
        return cls(
            vision=read("01_vision.md"),
            rules=read("02_rules.md"),
            adr=read("03_adr.md"),
        )

    def as_system_context(self) -> str:
        """Retorna el contenido como bloque de contexto de sistema."""
        parts = []
        if self.vision:
            parts.append(f"## Vision\n{self.vision}")
        if self.rules:
            parts.append(f"## Reglas\n{self.rules}")
        if self.adr:
            parts.append(f"## ADRs\n{self.adr}")
        return "\n\n".join(parts)


# ===========================================================================
# Failure Atlas — Registro curado de errores
# ===========================================================================

@dataclass
class FailureEntry:
    id: str
    error_type: str
    description: str
    context: dict
    solution: str
    tags: list[str]     = field(default_factory=list)
    occurred_at: str    = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


class ErrorRegistry:
    def __init__(self, store_path: Path) -> None:
        self._path = store_path
        self._path.mkdir(parents=True, exist_ok=True)

    def record(self, entry: FailureEntry) -> None:
        file = self._path / f"{entry.id}.json"
        file.write_text(json.dumps(entry.to_dict(), indent=2, ensure_ascii=False))

    def search(self, error_type: str) -> list[FailureEntry]:
        results = []
        for f in self._path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if data.get("error_type") == error_type:
                    results.append(FailureEntry(**data))
            except Exception:
                continue
        return results

    def all(self) -> list[FailureEntry]:
        results = []
        for f in self._path.glob("*.json"):
            try:
                results.append(FailureEntry(**json.loads(f.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return sorted(results, key=lambda e: e.occurred_at, reverse=True)


# ===========================================================================
# Pattern Library — Patrones aprobados
# ===========================================================================

@dataclass
class PatternEntry:
    id: str
    name: str
    description: str
    pattern_type: str       # "code", "workflow", "prompt", "tool_sequence"
    content: str
    tags: list[str]         = field(default_factory=list)
    success_count: int      = 0
    created_at: str         = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


class ApprovedPatternStore:
    def __init__(self, store_path: Path) -> None:
        self._path = store_path
        self._path.mkdir(parents=True, exist_ok=True)

    def add(self, entry: PatternEntry) -> None:
        file = self._path / f"{entry.id}.json"
        file.write_text(json.dumps(entry.to_dict(), indent=2, ensure_ascii=False))

    def get(self, pattern_id: str) -> PatternEntry | None:
        f = self._path / f"{pattern_id}.json"
        if not f.exists():
            return None
        return PatternEntry(**json.loads(f.read_text(encoding="utf-8")))

    def search_by_tag(self, tag: str) -> list[PatternEntry]:
        results = []
        for f in self._path.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if tag in data.get("tags", []):
                    results.append(PatternEntry(**data))
            except Exception:
                continue
        return results

    def all(self) -> list[PatternEntry]:
        results = []
        for f in self._path.glob("*.json"):
            try:
                results.append(PatternEntry(**json.loads(f.read_text(encoding="utf-8"))))
            except Exception:
                continue
        return results


# ===========================================================================
# Performance Ledger — Metricas de proveedores y herramientas
# ===========================================================================

@dataclass
class PerformanceSample:
    provider: str
    tool_or_model: str
    latency_ms: float
    success: bool
    cost_tokens: int        = 0
    error_type: str | None  = None
    sampled_at: str         = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return asdict(self)


class ProviderMetricsStore:
    def __init__(self, store_path: Path) -> None:
        self._path = store_path / "performance.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, sample: PerformanceSample) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sample.to_dict(), ensure_ascii=False) + "\n")

    def get_stats(self, provider: str) -> dict[str, Any]:
        samples = [
            s for s in self._read_all() if s.provider == provider
        ]
        if not samples:
            return {"provider": provider, "count": 0}
        success_count = sum(1 for s in samples if s.success)
        avg_latency = sum(s.latency_ms for s in samples) / len(samples)
        return {
            "provider": provider,
            "count": len(samples),
            "success_rate": success_count / len(samples),
            "avg_latency_ms": round(avg_latency, 2),
        }

    def _read_all(self) -> list[PerformanceSample]:
        if not self._path.exists():
            return []
        results = []
        with self._path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        results.append(PerformanceSample(**json.loads(line)))
                    except Exception:
                        continue
        return results


# ===========================================================================
# Tool Registry — Inventario de herramientas
# ===========================================================================

class ToolRegistry:
    """Inventario en memoria de todas las herramientas registradas en Atlas."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self._load_defaults()

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def enabled(self) -> list[Tool]:
        return [t for t in self._tools.values() if t.enabled]

    def by_level(self, level: ToolLevel) -> list[Tool]:
        return [t for t in self._tools.values() if t.level == level]

    def _load_defaults(self) -> None:
        defaults = [
            Tool("fs.read_file",        "Lee contenido de archivo en workspace",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("fs.list_dir",         "Lista contenido de directorio en workspace",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("fs.write_file",       "Escribe o modifica archivo en workspace",
                 ToolLevel.L_DET, PermissionLevel.CONFIRM),
            Tool("fs.create_dir",       "Crea directorio en workspace",
                 ToolLevel.L_DET, PermissionLevel.CONFIRM),
            Tool("fs.delete_file",      "Elimina archivo en workspace",
                 ToolLevel.L_DET, PermissionLevel.APPROVE),
            Tool("git.status",          "Estado del repositorio git",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("git.log",             "Historial de commits",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("git.diff",            "Diferencias actuales",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("git.add",             "Staging de cambios",
                 ToolLevel.L_DET, PermissionLevel.CONFIRM),
            Tool("git.commit",          "Commit de cambios",
                 ToolLevel.L_DET, PermissionLevel.CONFIRM),
            Tool("git.push",            "Push a remoto",
                 ToolLevel.L_DET, PermissionLevel.APPROVE),
            Tool("shell.run_allowlisted","Ejecuta comando de la allowlist",
                 ToolLevel.L_DET, PermissionLevel.CONFIRM),
            Tool("search.ripgrep",      "Busqueda de texto en workspace",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("search.agentgrep",    "Busqueda de codigo orientada a agentes",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("atlas.status",        "Estado del core de Atlas",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
            Tool("atlas.memory_read",   "Lee capa de memoria especificada",
                 ToolLevel.L_DET, PermissionLevel.AUTO),
        ]
        for t in defaults:
            self._tools[t.name] = t
