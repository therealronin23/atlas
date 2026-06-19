"""
Atlas Immunity — DeterministicMutator: diversidad léxica/superficial controlable.

Genera REFORMULACIONES deterministas de un texto. Límite honesto obligatorio:
las transformaciones son superficiales (reordenación, sustitución léxica cerrada,
leetspeak, espaciado). NO garantizan equivalencia semántica. El uso correcto es:

  (a) Inyectar diversidad en el ciclo de co-evolución de AffinityMaturation para
      evitar el colapso de self-play descrito por CHASE (arXiv:2606.05523).
  (b) Instrumento de MEDIDA: barrer mutate_at_distance(text, d) de 0.0 a 1.0
      produce variantes a "distancia" creciente, permitiendo trazar la curva de
      generalización del recaller. La monotonía es tendencia estadística, no
      garantía estricta.

Dependencias: stdlib únicamente (random, re, string).
"""

from __future__ import annotations

import random
import re
import string
from typing import Final

# ---------------------------------------------------------------------------
# Tabla de sinónimos cerrada (sin deps externas).
# Suficiente para inyectar diversidad léxica superficial en el dominio de
# seguridad. Ampliar si el dominio lo requiere, pero nunca con WordNet/NLTK.
# ---------------------------------------------------------------------------
_SYNONYMS: Final[dict[str, list[str]]] = {
    "avoid": ["skip", "bypass", "ignore", "evade"],
    "detect": ["identify", "find", "spot", "recognize"],
    "check": ["verify", "validate", "inspect", "examine"],
    "input": ["data", "payload", "text", "content"],
    "user": ["client", "caller", "requester", "agent"],
    "attack": ["exploit", "threat", "payload", "injection"],
    "pattern": ["template", "signature", "form", "structure"],
    "rule": ["constraint", "policy", "guard", "check"],
    "block": ["reject", "deny", "stop", "halt"],
    "allow": ["permit", "accept", "pass", "approve"],
    "execute": ["run", "invoke", "call", "trigger"],
    "output": ["result", "response", "reply", "answer"],
    "code": ["script", "program", "snippet", "fragment"],
    "function": ["method", "routine", "procedure", "call"],
    "error": ["fault", "failure", "exception", "bug"],
    "system": ["platform", "environment", "runtime", "host"],
    "access": ["reach", "entry", "permission", "privilege"],
    "inject": ["insert", "embed", "push", "add"],
    "escape": ["evade", "break", "exit", "bypass"],
    "filter": ["sanitize", "clean", "strip", "remove"],
}

# Mapa leetspeak determinista (subconjunto pequeño para legibilidad).
_LEET: Final[dict[str, str]] = {"a": "4", "e": "3", "i": "1", "o": "0"}

# Tokens de relleno que se pueden insertar sin cambiar semántica de ataque.
_FILLER_TOKENS: Final[tuple[str, ...]] = (
    "basically",
    "simply",
    "actually",
    "indeed",
    "notably",
    "specifically",
    "clearly",
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _apply_synonyms(tokens: list[str], rng: random.Random, prob: float) -> list[str]:
    """Sustituye tokens por sinónimos de la tabla cerrada con probabilidad prob."""
    result: list[str] = []
    for tok in tokens:
        key = tok.lower().strip(string.punctuation)
        if key in _SYNONYMS and rng.random() < prob:
            replacement = rng.choice(_SYNONYMS[key])
            # Preservar mayúscula inicial si el token la tiene.
            if tok and tok[0].isupper():
                replacement = replacement.capitalize()
            result.append(replacement)
        else:
            result.append(tok)
    return result


def _apply_leet(tokens: list[str], rng: random.Random, prob: float) -> list[str]:
    """Aplica leetspeak parcial a caracteres aleatorios de cada token."""
    result: list[str] = []
    for tok in tokens:
        chars = list(tok)
        for idx, ch in enumerate(chars):
            if ch.lower() in _LEET and rng.random() < prob:
                replacement = _LEET[ch.lower()]
                chars[idx] = replacement
        result.append("".join(chars))
    return result


def _apply_reorder(tokens: list[str], rng: random.Random, prob: float) -> list[str]:
    """Permuta aleatoriamente hasta una fracción `prob` de tokens adyacentes."""
    if len(tokens) < 2:
        return tokens[:]
    result = tokens[:]
    n_swaps = max(1, int(len(result) * prob * 0.5))
    for _ in range(n_swaps):
        i = rng.randint(0, len(result) - 2)
        result[i], result[i + 1] = result[i + 1], result[i]
    return result


def _apply_filler(tokens: list[str], rng: random.Random, prob: float) -> list[str]:
    """Inserta tokens de relleno en posiciones aleatorias con probabilidad prob."""
    if not tokens or rng.random() >= prob:
        return tokens[:]
    result = tokens[:]
    insert_pos = rng.randint(0, len(result))
    filler = rng.choice(_FILLER_TOKENS)
    result.insert(insert_pos, filler)
    return result


def _apply_case_variation(tokens: list[str], rng: random.Random, prob: float) -> list[str]:
    """Varía mayúsculas/minúsculas en tokens con probabilidad prob."""
    result: list[str] = []
    for tok in tokens:
        if rng.random() < prob:
            variant = rng.choice([tok.lower(), tok.upper(), tok.capitalize()])
            result.append(variant)
        else:
            result.append(tok)
    return result


# ---------------------------------------------------------------------------
# DeterministicMutator
# ---------------------------------------------------------------------------


class DeterministicMutator:
    """
    Mutador determinista de texto para diversidad léxica/superficial.

    Mismo (texto, seed, intensity) siempre produce la misma salida.
    Instancias independientes con el mismo seed son equivalentes.

    ``intensity`` ∈ [0.0, 1.0] controla qué transformaciones se aplican y
    con qué probabilidad. intensity=0.0 devuelve el texto original intacto.

    Transformaciones (aplicadas en orden):
      1. Sustitución por sinónimos de tabla cerrada.
      2. Reordenación de tokens adyacentes.
      3. Inserción de relleno.
      4. Leetspeak parcial.
      5. Variación de mayúsculas/espaciado.

    Límite: la salida puede no ser gramaticalmente correcta ni semánticamente
    equivalente al original. Es diversidad superficial, no paráfrasis real.
    """

    def __init__(self, *, intensity: float = 0.3, seed: int = 0) -> None:
        if not (0.0 <= intensity <= 1.0):
            raise ValueError(f"intensity debe estar en [0, 1], recibido {intensity}")
        self.intensity = intensity
        self.seed = seed

    def _make_rng(self, text: str, extra: float = 0.0) -> random.Random:
        """RNG determinista derivado de (seed, text, extra)."""
        # Combinamos con hash del texto para que textos distintos con el mismo
        # seed produzcan mutaciones distintas.
        combined = (self.seed, text, round(extra, 6))
        return random.Random(hash(combined))

    def mutate(self, text: str) -> str:
        """Devuelve una variante superficial del texto con ``self.intensity``."""
        return self.mutate_at_distance(text, self.intensity)

    def mutate_at_distance(self, text: str, distance: float) -> str:
        """
        Produce una variante a distancia léxica objetivo ``distance`` ∈ [0, 1].

        Determinista: (text, distance) → misma salida siempre.
        La monotonía (mayor distance → mayor diferencia) es una TENDENCIA
        estadística promediada sobre varios textos, no una garantía estricta
        por llamada individual.
        """
        if not text:
            return text
        if distance <= 0.0:
            return text

        d = min(1.0, max(0.0, distance))
        rng = self._make_rng(text, extra=d)

        tokens = text.split()
        if not tokens:
            return text

        # Escalonamos la probabilidad de cada transformación según distancia.
        # Orden importa: empezamos por las más suaves.
        if d >= 0.1:
            tokens = _apply_synonyms(tokens, rng, prob=d * 0.6)
        if d >= 0.25:
            tokens = _apply_reorder(tokens, rng, prob=d * 0.5)
        if d >= 0.4:
            tokens = _apply_filler(tokens, rng, prob=d * 0.4)
        if d >= 0.55:
            tokens = _apply_leet(tokens, rng, prob=d * 0.35)
        if d >= 0.7:
            tokens = _apply_case_variation(tokens, rng, prob=d * 0.3)

        result = " ".join(tokens)
        # Normalizar espacios múltiples que puedan introducir las transformaciones.
        result = re.sub(r"  +", " ", result).strip()
        return result if result else text
