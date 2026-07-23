"""
Atlas Core — MemoryRecord: el contrato genérico del sustrato de memoria verificable.

El MOTOR (índice persistente + abstractor) es agnóstico de dominio: solo necesita
de cada cosa que recuerda un `record_id`, un `text` representativo (lo que se
embebe) y un `created_at`. La memoria inmune de ciberseguridad (`Lesson`) es UN
inquilino que se adapta a este contrato; mañana habrá otros. El motor no sabe qué
es una lección, ni qué es Garak.

`record_type` lleva la taxonomía de conocimiento (analytic | empirical | episodic)
que gobernará la política de olvido/supersesión en 1d. El motor la transporta pero
todavía NO ramifica sobre ella (no se construye lógica antes de necesitarla).

`fact_valid_at_ns`/`fact_invalid_at_ns` (mem-1) distinguen el tiempo del HECHO
(cuándo algo fue/dejó de ser cierto EN EL MUNDO) del tiempo de SISTEMA que ya
llevaba el índice (`valid_from_ns`/`valid_until_ns` en `SqliteMemoryIndex`: cuándo
el sistema lo ingirió/invalidó). Son OPCIONALES — default None — precisamente
porque la mayoría de las memorias se ingieren en el momento en que pasan a ser
ciertas (sistema ≈ hecho) y no aportan nada distinguirlos; solo importan cuando
un hecho pasado se ingiere tarde (ver docs/inbox/graphiti_dissection_2026-07-10.md#1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class MemoryRecord(Protocol):
    """Lo mínimo que el motor necesita de cualquier cosa memorizable."""

    @property
    def record_id(self) -> str: ...

    @property
    def text(self) -> str: ...

    @property
    def created_at(self) -> str: ...

    @property
    def fact_valid_at_ns(self) -> int | None: ...

    @property
    def fact_invalid_at_ns(self) -> int | None: ...


@dataclass(frozen=True)
class GenericRecord:
    """Registro genérico de propósito general (cualquier dominio).

    `record_type`: analytic | empirical | episodic (taxonomía; reservado para 1d).
    `fact_valid_at_ns`/`fact_invalid_at_ns`: tiempo del HECHO, opcional (mem-1;
    ver docstring del módulo). None (default) = sin distinguir del tiempo de
    sistema del índice — cero cambio de comportamiento para quien no los use.
    """

    record_id: str
    text: str
    created_at: str = ""
    record_type: str | None = None
    fact_valid_at_ns: int | None = None
    fact_invalid_at_ns: int | None = None
