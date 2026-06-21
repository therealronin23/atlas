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


@dataclass(frozen=True)
class GenericRecord:
    """Registro genérico de propósito general (cualquier dominio).

    `record_type`: analytic | empirical | episodic (taxonomía; reservado para 1d).
    """

    record_id: str
    text: str
    created_at: str = ""
    record_type: str | None = None
