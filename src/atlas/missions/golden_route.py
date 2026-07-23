"""Ruta dorada de autoconstrucción (Foundry v0, ADR-069).

La superficie PÚBLICA con la que Atlas se mejora a sí mismo con gobierno:

    request(texto) → plan mínimo → worktree aislado (motor ColdUpdate)
    → execute(): validación observable → diff visible
    → approve(actor, decision): ceremonia humana registrada en Merkle
    → apply(): el MOTOR aplica y commitea con evidencia → receipt + audit_ref

No reimplementa nada: ENVUELVE ColdUpdateManager (ADR-025), que ya sabe de
worktrees, patches, validación pytest/mypy, rollback y commits con evidencia.
Lo que añade es lo que faltaba (export Diseño UI Atlas L45286): la ruta única
pública, el plan acotado, la ceremonia de aprobación explícita (PermissionError
sin decisión humana) y el receipt verificable.

v0 era DELIBERADAMENTE acotada: solo cambios documentation-only (append de una
línea a un fichero bajo docs/). Sin LLM: la petición se parsea determinista;
lo que no entiende se rechaza con honestidad (UnsupportedRequestError), no se
improvisa.

T1.1 (ADR-069, plan maestro) amplía el vocabulario con un SEGUNDO patrón
determinista de cambio de código acotado: "renombra X a Y en <fichero>"
(reemplazo léxico whole-word de un identificador dentro de un único fichero,
bajo los mismos prefijos que ColdUpdateManager ya acepta: src/ tests/
scripts/ docs/ config/). Sigue sin haber LLM libre decidiendo el plan: sigue
siendo parseo determinista + rechazo honesto (UnsupportedRequestError) para
lo que no entra en el vocabulario. Ampliar más el vocabulario sigue siendo
trabajo futuro.

T1.2 (Foundry Fase C, ADR-069): primera soul ejecutable, `devil_advocate`
(`atlas.missions.souls.devil_advocate`), enganchada vía
`GoldenRouteSession.soul_review()` — un paso EXPLÍCITO antes de `approve()`,
nunca automático ni oculto. La soul solo informa (invariante D2 intacta): su
veredicto se registra en Merkle y queda disponible en `session.soul_verdict`,
pero `approve()` sigue exigiendo la misma ceremonia humana de siempre — un
humano decide, informado por la objeción, no sustituido por ella.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Any, Callable, Protocol

from atlas.api.missions import mission_receipt, proposal_to_mission
from atlas.core.cold_update_manager import ColdUpdateManager, ColdUpdateProposal
from atlas.logging.merkle_logger import MerkleLogger
from atlas.missions.souls.devil_advocate import DevilAdvocateVerdict, review_mission

__all__ = [
    "GoldenRoute",
    "GoldenRouteSession",
    "GoldenRouteResult",
    "UnsupportedRequestError",
    "plan_from_request",
    "unified_patch_for_append",
    "unified_patch_for_rename",
]


class UnsupportedRequestError(ValueError):
    """La petición está fuera del vocabulario acotado de la ruta v0."""


class _RunnerLike(Protocol):
    def run(self, timeout_s: int = 600) -> Any: ...


class _SoulHubLike(Protocol):
    """Lo mínimo que `soul_review` necesita del hub de inferencia (mismo
    patrón que `_RunnerLike`): permite dobles de test sin acoplar la ruta
    dorada a InferenceHub completo."""

    def infer_for_role(self, role: str, request: Any) -> Any: ...


_QUOTED_RE = re.compile(
    r"^añade la línea [\"“](?P<line>.+?)[\"”] al final de (?P<path>\S+)$",
    re.IGNORECASE,
)
_DEFAULT_RE = re.compile(
    r"^añade una línea al final de (?P<path>\S+)$",
    re.IGNORECASE,
)
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_RENAME_RE = re.compile(
    rf"^renombra (?P<old>{_IDENTIFIER}) a (?P<new>{_IDENTIFIER}) en (?P<path>\S+)$",
    re.IGNORECASE,
)

# Mismos prefijos que ColdUpdateManager.ALLOWED_PREFIXES (y el guard gemelo
# de codegen_proposer._ALLOWED_PREFIXES): el motor ya sabe aplicar/commitear
# patches de código ahí — el hueco de T1.1 era solo de vocabulario/parsing.
_CODE_ALLOWED_PREFIXES = ("src", "tests", "scripts", "docs", "config")


def _validate_doc_path(raw: str) -> str:
    """v0 es documentation-only: solo rutas relativas bajo docs/, sin escapes."""
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise UnsupportedRequestError(f"Ruta absoluta no permitida: {raw}")
    if ".." in path.parts:
        raise UnsupportedRequestError(f"Ruta con escape no permitida: {raw}")
    if path.parts[:1] != ("docs",):
        raise UnsupportedRequestError(
            f"La ruta dorada v0 es documentation-only (docs/): {raw}"
        )
    return str(path)


def _validate_code_path(raw: str) -> str:
    """Patrón 'renombra': cambio de código acotado a UN fichero bajo los
    mismos prefijos que el motor ya acepta (allowed_paths = ese único
    fichero — el patch generado nunca toca otra ruta)."""
    path = PurePosixPath(raw)
    if path.is_absolute():
        raise UnsupportedRequestError(f"Ruta absoluta no permitida: {raw}")
    if ".." in path.parts:
        raise UnsupportedRequestError(f"Ruta con escape no permitida: {raw}")
    if path.parts[:1] not in {(prefix,) for prefix in _CODE_ALLOWED_PREFIXES}:
        raise UnsupportedRequestError(
            "La ruta dorada solo acepta cambios bajo "
            f"{_CODE_ALLOWED_PREFIXES}: {raw}"
        )
    return str(path)


def plan_from_request(text: str) -> dict[str, str]:
    """Parsea la petición al plan mínimo. Determinista, sin LLM: lo que no
    entra en el vocabulario v0 se rechaza con mensaje honesto."""
    cleaned = " ".join(text.split())
    match = _QUOTED_RE.match(cleaned)
    if match:
        return {
            "action": "append_line",
            "path": _validate_doc_path(match.group("path")),
            "line": match.group("line"),
        }
    match = _DEFAULT_RE.match(cleaned)
    if match:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return {
            "action": "append_line",
            "path": _validate_doc_path(match.group("path")),
            "line": f"<!-- ruta dorada: línea añadida el {stamp} -->",
        }
    match = _RENAME_RE.match(cleaned)
    if match:
        return {
            "action": "rename_identifier",
            "path": _validate_code_path(match.group("path")),
            "old": match.group("old"),
            "new": match.group("new"),
        }
    raise UnsupportedRequestError(
        "La ruta dorada v0 solo sabe hacer esto: "
        "'añade una línea al final de docs/<fichero>', "
        "'añade la línea \"<contenido>\" al final de docs/<fichero>' o "
        "'renombra <X> a <Y> en <fichero>'. "
        f"Petición recibida: {text!r}"
    )


def unified_patch_for_append(path: str, current: str, line: str) -> str:
    """Diff unificado (aplicable con `git apply`/`patch -p1`) que añade una
    línea al final del fichero. Construido a mano para controlar el caso
    'sin newline final' (la última línea se reescribe con newline)."""
    if current == "":
        # Fichero de 0 bytes: hunk de inserción pura. Un @@ -1,1 ... sobre la
        # "línea vacía" que devuelve split() lo rechazan git apply y patch.
        header = [f"--- a/{path}", f"+++ b/{path}", "@@ -0,0 +1 @@", f"+{line}"]
        return "\n".join(header) + "\n"
    lines = current.split("\n")
    ends_with_newline = current.endswith("\n")
    if ends_with_newline:
        lines = lines[:-1]  # split deja un "" final

    total = len(lines)
    context = lines[-3:] if total >= 3 else lines
    start = total - len(context) + 1

    out: list[str] = [f"--- a/{path}", f"+++ b/{path}"]
    old_count = len(context)
    if ends_with_newline:
        new_count = old_count + 1
        out.append(f"@@ -{start},{old_count} +{start},{new_count} @@")
        out.extend(f" {c}" for c in context)
        out.append(f"+{line}")
    else:
        # la última línea sin newline se reescribe (con newline) + la nueva
        new_count = old_count + 1
        out.append(f"@@ -{start},{old_count} +{start},{new_count} @@")
        out.extend(f" {c}" for c in context[:-1])
        out.append(f"-{context[-1]}")
        out.append("\\ No newline at end of file")
        out.append(f"+{context[-1]}")
        out.append(f"+{line}")
    return "\n".join(out) + "\n"


def unified_patch_for_rename(path: str, current: str, old: str, new: str) -> str:
    """Diff unificado (aplicable con `git apply`/`patch -p1`) que renombra un
    identificador dentro de UN fichero: sustitución léxica whole-word (nunca
    substring — "old" no toca "old_name"), generada con difflib para
    soportar el multi-línea sin patch a mano como el de append."""
    pattern = re.compile(rf"\b{re.escape(old)}\b")
    updated, count = pattern.subn(new, current)
    if count == 0:
        raise UnsupportedRequestError(
            f"'{old}' no aparece (como identificador completo) en {path}"
        )
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    return "".join(diff)


@dataclass
class GoldenRouteResult:
    """Cierre de una sesión de ruta dorada: recibo humano + ref de auditoría."""

    proposal_id: str
    status: str
    receipt: dict[str, Any]
    audit_ref: str


class GoldenRouteSession:
    """Una petición viva recorriendo la ruta. El estado usa el vocabulario de
    misión (schemas/mission.schema.json), derivado SIEMPRE del ledger real."""

    def __init__(
        self,
        manager: ColdUpdateManager,
        merkle: MerkleLogger,
        proposal: ColdUpdateProposal,
        plan: dict[str, str],
    ) -> None:
        self._manager = manager
        self._merkle = merkle
        self._proposal_id = proposal.id
        self.plan: dict[str, str] = plan
        self._approval: dict[str, str] | None = None
        self._soul_verdict: DevilAdvocateVerdict | None = None

    # -- lecturas derivadas del ledger (nunca estado duplicado) -----------

    def _proposal(self) -> ColdUpdateProposal:
        proposal = self._manager.get(self._proposal_id)
        if proposal is None:  # pragma: no cover — solo si borran el ledger
            raise RuntimeError(f"Propuesta desaparecida: {self._proposal_id}")
        return proposal

    @property
    def proposal_id(self) -> str:
        return self._proposal_id

    @property
    def state(self) -> str:
        return str(proposal_to_mission(self._proposal().to_dict())["state"])

    @property
    def worktree_path(self) -> Path | None:
        raw = self._proposal().worktree_path
        return Path(raw) if raw else None

    @property
    def diff(self) -> str:
        """El patch real almacenado por el motor — diff visible o no cuenta."""
        try:
            return Path(self._proposal().patch_path).read_text(encoding="utf-8")
        except OSError:
            return ""

    @property
    def validation(self) -> dict[str, Any] | None:
        return self._proposal().validation

    @property
    def soul_verdict(self) -> DevilAdvocateVerdict | None:
        """Último veredicto de `soul_review()`, o `None` si nunca se invocó
        (invocarla es un paso explícito de la ruta, no automático)."""
        return self._soul_verdict

    # -- transiciones -------------------------------------------------------

    def execute(self) -> dict[str, Any]:
        """Valida el cambio en el worktree (checks observables del motor)."""
        report = self._manager.validate(self._proposal_id)
        return dict(report.to_dict())

    def soul_review(self, hub: _SoulHubLike) -> DevilAdvocateVerdict:
        """Invoca la soul `devil_advocate` (Foundry Fase C, ADR-069, T1.2)
        sobre la misión ACTUAL, un paso explícito antes de `approve()`.

        Invariante D2 intacta: la soul nunca aprueba, rechaza ni aplica nada
        — solo informa. El veredicto se registra en Merkle de forma
        verificable (`golden_route.soul_reviewed`) y queda expuesto en
        `self.soul_verdict`; si luego se llama a `approve()`, el veredicto
        viaja también en ESE registro (`payload["soul_verdict"]`) para que
        la decisión humana y la objeción queden ligadas en una sola entrada
        auditable."""
        mission = proposal_to_mission(self._proposal().to_dict())
        verdict = review_mission(mission, hub=hub)
        self._soul_verdict = verdict
        self._merkle.log(
            action="golden_route.soul_reviewed",
            agent="golden_route.soul_devil_advocate",
            result="success",
            risk_level="high",
            payload={
                "proposal_id": self._proposal_id,
                "verdict": verdict.to_dict(),
            },
        )
        return verdict

    def approve(self, *, actor: str, decision: str) -> None:
        """Ceremonia humana explícita, registrada en Merkle ANTES de actuar."""
        if decision not in {"approve", "reject"}:
            raise ValueError("decision debe ser 'approve' o 'reject'")
        record = self._merkle.log(
            action=f"golden_route.decision.{decision}",
            agent="golden_route",
            result="success",
            risk_level="critical",
            payload={
                "proposal_id": self._proposal_id,
                "actor": actor,
                "decision": decision,
                "plan": self.plan,
                "soul_verdict": (
                    self._soul_verdict.to_dict() if self._soul_verdict else None
                ),
            },
        )
        if decision == "approve":
            self._manager.approve(self._proposal_id)
        else:
            self._manager.reject(
                self._proposal_id, reason=f"rechazada por {actor} (ruta dorada)"
            )
        # Solo tras aceptar el motor la transición: si lanzó, esta sesión NO
        # queda marcada como decidida (el ledger es la verdad, no este objeto).
        self._approval = {
            "actor": actor,
            "decision": decision,
            "audit_ref": record.hash_self,
        }

    def apply(self) -> GoldenRouteResult:
        """Aplica SOLO con aprobación humana registrada. El motor re-valida
        post-apply, commitea con evidencia y hace rollback si algo falla."""
        if self._approval is None:
            raise PermissionError(
                "La ruta dorada exige aprobación humana registrada antes de "
                "aplicar: session.approve(actor=..., decision='approve')"
            )
        if self._approval["decision"] != "approve":
            raise PermissionError(
                "La decisión humana registrada fue rechazar; no hay apply."
            )
        self._manager.apply(self._proposal_id)

        proposal = self._proposal()
        receipt = mission_receipt(
            proposal.to_dict(), files_touched=[self.plan["path"]]
        )
        record = self._merkle.log(
            action="golden_route.applied",
            agent="golden_route",
            result="success",
            risk_level="critical",
            payload={
                "proposal_id": self._proposal_id,
                "receipt_id": receipt["receipt_id"],
                "path": self.plan["path"],
                "approved_by": self._approval["actor"],
                "approval_ref": self._approval["audit_ref"],
            },
        )
        return GoldenRouteResult(
            proposal_id=self._proposal_id,
            status=proposal.status,
            receipt=receipt,
            audit_ref=record.hash_self,
        )


class GoldenRoute:
    """Fábrica de sesiones de la ruta dorada sobre un motor ColdUpdate real."""

    def __init__(self, manager: ColdUpdateManager, merkle: MerkleLogger) -> None:
        self._manager = manager
        self._merkle = merkle

    @classmethod
    def for_repo(
        cls,
        repo_root: Path,
        *,
        store_dir: Path,
        audit_dir: Path,
        runner_factory: Callable[[Path], _RunnerLike] | None = None,
    ) -> "GoldenRoute":
        """Constructor de conveniencia (tests/fixture repos y uso directo)."""
        merkle = MerkleLogger(audit_dir)
        manager = ColdUpdateManager(
            repo_root,
            merkle,
            store_dir=store_dir,
            runner_factory=runner_factory,  # type: ignore[arg-type]
        )
        return cls(manager, merkle)

    def request(
        self, text: str, *, risk: str = "low"
    ) -> GoldenRouteSession:
        """Petición → plan → patch → propuesta real (worktree aislado)."""
        plan = plan_from_request(text)
        root: Path = self._manager._root  # noqa: SLF001 — ver nota abajo
        # Nota: leer la raíz del motor es intencionado (misma raíz que usará
        # apply); el contenido base se lee del árbol en HEAD-igual-que-worktree.
        target = root / plan["path"]
        if target.is_symlink():
            # Sin esto el bloqueo dependería de que git apply/patch rechacen
            # "not a regular file" — herramienta externa, no garantía nuestra.
            raise UnsupportedRequestError(
                f"La ruta es un symlink y la ruta dorada no los sigue: "
                f"{plan['path']}"
            )
        if not target.is_file():
            raise UnsupportedRequestError(
                f"No existe o no es un fichero regular: {plan['path']} "
                "(la ruta dorada solo modifica ficheros ya existentes)"
            )
        current = target.read_text(encoding="utf-8")
        if plan["action"] == "rename_identifier":
            patch_text = unified_patch_for_rename(
                plan["path"], current, plan["old"], plan["new"]
            )
        else:
            patch_text = unified_patch_for_append(
                plan["path"], current, plan["line"]
            )
        with NamedTemporaryFile(
            "w", suffix=".patch", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(patch_text)
            patch_file = Path(handle.name)
        try:
            proposal = self._manager.propose(
                text,
                patch_file,
                origin="manual",
                risk=risk,
                evidence={"golden_route": True, "plan": plan},
            )
        finally:
            patch_file.unlink(missing_ok=True)
        self._merkle.log(
            action="golden_route.requested",
            agent="golden_route",
            result="success",
            risk_level="high",
            payload={"proposal_id": proposal.id, "request": text, "plan": plan},
        )
        return GoldenRouteSession(self._manager, self._merkle, proposal, plan)
