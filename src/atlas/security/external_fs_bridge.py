"""
Atlas Core — External FS Bridge
Punto unico de acceso al sistema de ficheros desde el sandbox local.
Solo el External FS Bridge puede leer/escribir ficheros fuera del sandbox.
Aplica la misma disciplina que SSRFBridge pero para rutas de ficheros.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FsDecision:
    allowed: bool
    path: str
    reason: str
    resolved_path: str | None


class ExternalFsBridge:
    """
    Proxy de acceso al sistema de ficheros para codigo en sandbox.
    Evalua rutas antes de permitir operaciones de fichero.
    El codigo en sandbox llama a ExternalFsBridge.check() antes de hacer
    cualquier operacion de fichero externo.
    """

    def __init__(self, extra_roots: set[str] | None = None) -> None:
        self._roots: set[Path] = set()
        for root in extra_roots or set():
            self._roots.add(Path(root).resolve())

    def check(self, path: str) -> FsDecision:
        """
        Evalua si una ruta de fichero puede ser accedida desde el sandbox.
        Retorna FsDecision con allowed=True si esta permitida.

        Orden de evaluacion (defensa en profundidad):
          1. Resuelve la ruta con Path.resolve() (elimina '../', symlinks, etc.).
          2. Comprueba si la ruta resuelta es sub-path de algun extra_root.
          3. Fail-closed: si no hay match, deniega.
        """
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError) as exc:
            return FsDecision(
                allowed=False,
                path=path,
                reason=f"Ruta invalida: {exc}",
                resolved_path=None,
            )

        if not self._roots:
            return FsDecision(
                allowed=False,
                path=path,
                reason="No hay roots configurados (fail-closed).",
                resolved_path=str(resolved),
            )

        for root in self._roots:
            try:
                if resolved.is_relative_to(root):
                    return FsDecision(
                        allowed=True,
                        path=path,
                        reason=f"Ruta dentro de root permitido: {root}",
                        resolved_path=str(resolved),
                    )
            except ValueError:
                # is_relative_to puede lanzar ValueError en casos extremos
                continue

        return FsDecision(
            allowed=False,
            path=path,
            reason=f"Ruta resuelta fuera de todos los roots permitidos: {resolved}",
            resolved_path=str(resolved),
        )

    def add_root(self, path: str) -> None:
        """Anade un root al filesystem en runtime (requiere APPROVE)."""
        self._roots.add(Path(path).resolve())

    @property
    def allowed_roots(self) -> frozenset[str]:
        return frozenset(str(root) for root in self._roots)
