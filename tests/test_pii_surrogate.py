"""
Tests de PIISurrogate (ADR-023, Gate D/D6).
Verifica deteccion por tipo, determinismo del surrogate, redact + restore
roundtrip, edge cases y formato valido del surrogate generado.
"""

from __future__ import annotations

import re

import pytest

from atlas.security.pii_surrogate import (
    PIIMatch,
    PIISurrogate,
    PIIType,
    RedactionResult,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def surrogate() -> PIISurrogate:
    return PIISurrogate(salt="test-salt-fixed")


# ===========================================================================
# Deteccion por tipo
# ===========================================================================


class TestDetectByType:

    def test_detect_email(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("contactame en ronin@gmail.com pls")
        assert len(matches) == 1
        assert matches[0].type == PIIType.EMAIL
        assert matches[0].original == "ronin@gmail.com"

    def test_detect_dni(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("mi DNI es 12345678Z y caduca pronto")
        assert any(m.type == PIIType.DNI for m in matches)

    def test_detect_iban(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("cuenta ES9121000418450200051332")
        assert any(m.type == PIIType.IBAN for m in matches)

    def test_detect_phone_es(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("llamame al +34 612 345 678")
        assert any(m.type == PIIType.PHONE_ES for m in matches)

    def test_detect_phone_es_compact(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("tel: 612345678")
        assert any(m.type == PIIType.PHONE_ES for m in matches)

    def test_detect_ipv4(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("VPS en 178.105.216.187")
        assert any(m.type == PIIType.IPV4 for m in matches)

    def test_detect_ipv6(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("v6 prefix 2a01:4f8:c015:488::1")
        assert any(m.type == PIIType.IPV6 for m in matches)

    def test_detect_name(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("Llamame Maria o Juan para confirmar")
        assert any(m.type == PIIType.NAME for m in matches)
        assert any(m.original.lower() in {"maria", "juan"} for m in matches)

    def test_detect_city(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("Estoy en Madrid y luego vuelvo a Valencia")
        assert any(m.type == PIIType.CITY for m in matches)
        assert any(m.original.lower() in {"madrid", "valencia"} for m in matches)

    def test_detect_address(self, surrogate: PIISurrogate) -> None:
        matches = surrogate.detect("Vivo en Calle Falsa 123 desde hace años")
        assert any(m.type == PIIType.ADDRESS for m in matches)
        assert matches[0].original.startswith("Calle Falsa")

    def test_detect_groq_key(self, surrogate: PIISurrogate) -> None:
        text = "GROQ_API_KEY=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"
        matches = surrogate.detect(text)
        assert any(m.type == PIIType.GROQ_API_KEY for m in matches)

    def test_detect_openrouter_key(self, surrogate: PIISurrogate) -> None:
        text = "OR: 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"
        matches = surrogate.detect(text)
        assert any(m.type == PIIType.OPENROUTER_API_KEY for m in matches)

    def test_no_match_clean_text(self, surrogate: PIISurrogate) -> None:
        assert surrogate.detect("hola mundo, nada sensible aqui") == []


# ===========================================================================
# Determinismo
# ===========================================================================


class TestDeterminism:

    def test_same_input_same_surrogate(self, surrogate: PIISurrogate) -> None:
        r1 = surrogate.redact("ping ronin@gmail.com").matches[0]
        r2 = surrogate.redact("hola ronin@gmail.com de nuevo").matches[0]
        assert r1.surrogate == r2.surrogate

    def test_different_salt_different_surrogate(self) -> None:
        a = PIISurrogate(salt="salt-A")
        b = PIISurrogate(salt="salt-B")
        sa = a.redact("ronin@gmail.com").matches[0].surrogate
        sb = b.redact("ronin@gmail.com").matches[0].surrogate
        assert sa != sb

    def test_different_input_different_surrogate(
        self, surrogate: PIISurrogate
    ) -> None:
        s1 = surrogate.redact("a@x.com").matches[0].surrogate
        s2 = surrogate.redact("b@x.com").matches[0].surrogate
        assert s1 != s2


# ===========================================================================
# Formato de surrogates (preservacion de utilidad semantica)
# ===========================================================================


class TestSurrogateFormat:

    def test_email_surrogate_is_email(self, surrogate: PIISurrogate) -> None:
        s = surrogate.redact("foo@bar.com").matches[0].surrogate
        assert "@" in s
        assert "." in s.split("@")[1]

    def test_dni_surrogate_is_dni(self, surrogate: PIISurrogate) -> None:
        s = surrogate.redact("12345678Z").matches[0].surrogate
        assert re.fullmatch(r"\d{8}[A-HJ-NP-TV-Z]", s)
        # Letra debe ser la correcta para los 8 digitos generados
        digits = s[:8]
        letters = "TRWAGMYFPDXBNJZSQVHLCKE"
        assert s[8] == letters[int(digits) % 23]

    def test_phone_surrogate_starts_with_es_prefix(
        self, surrogate: PIISurrogate
    ) -> None:
        s = surrogate.redact("612345678").matches[0].surrogate
        assert s.startswith("+34 ")

    def test_iban_surrogate_is_iban(self, surrogate: PIISurrogate) -> None:
        s = surrogate.redact("ES9121000418450200051332").matches[0].surrogate
        assert s.startswith("ES")
        assert len(s) == 24

    def test_ipv4_surrogate_in_testnet1(self, surrogate: PIISurrogate) -> None:
        s = surrogate.redact("178.105.216.187").matches[0].surrogate
        assert s.startswith("192.0.2.")

    def test_ipv6_surrogate_in_doc_range(self, surrogate: PIISurrogate) -> None:
        s = surrogate.redact("2a01:4f8:c015:488::1").matches[0].surrogate
        assert s.startswith("2001:db8:")

    def test_groq_surrogate_keeps_prefix(self, surrogate: PIISurrogate) -> None:
        original = "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"
        s = surrogate.redact(original).matches[0].surrogate
        assert s.startswith("gsk_")
        assert s != original

    def test_openrouter_surrogate_keeps_prefix(
        self, surrogate: PIISurrogate
    ) -> None:
        orig = "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"
        s = surrogate.redact(orig).matches[0].surrogate
        assert s.startswith("sk-or-v1-")


# ===========================================================================
# Redact + restore roundtrip
# ===========================================================================


class TestRoundtrip:

    def test_redact_returns_text_with_surrogates(
        self, surrogate: PIISurrogate
    ) -> None:
        result = surrogate.redact("mi email es a@b.com y mi DNI 12345678Z")
        assert "a@b.com" not in result.text
        assert "12345678Z" not in result.text
        assert len(result.mapping) == 2

    def test_restore_roundtrip(self, surrogate: PIISurrogate) -> None:
        original = (
            "Mi email: ronin@gmail.com\n"
            "Mi DNI: 12345678Z\n"
            "IBAN: ES9121000418450200051332"
        )
        result = surrogate.redact(original)
        # Simular respuesta del LLM que repite los surrogates
        llm_resp = (
            f"Recibi tu email {next(s for s in result.mapping if '@' in s)}. "
            f"Lo procesare."
        )
        restored = surrogate.restore(llm_resp, result.mapping)
        assert "ronin@gmail.com" in restored

    def test_multiple_occurrences_same_value_share_surrogate(
        self, surrogate: PIISurrogate
    ) -> None:
        result = surrogate.redact(
            "Avisa a a@b.com. Tambien copia a a@b.com en el reply."
        )
        # Dos matches con el mismo original -> mismo surrogate
        assert len(result.matches) == 2
        assert result.matches[0].surrogate == result.matches[1].surrogate

    def test_empty_text(self, surrogate: PIISurrogate) -> None:
        result = surrogate.redact("")
        assert result.text == ""
        assert result.matches == ()
        assert result.mapping == {}

    def test_no_pii_text(self, surrogate: PIISurrogate) -> None:
        text = "atlas core es soberano"
        result = surrogate.redact(text)
        assert result.text == text
        assert result.matches == ()

    def test_redact_restore_new_types_roundtrip(self, surrogate: PIISurrogate) -> None:
        original = "Mi nombre es Juan. Vivo en Calle Falsa 123, Madrid."
        result = surrogate.redact(original)
        assert any(m.type == PIIType.NAME for m in result.matches)
        assert any(m.type == PIIType.ADDRESS for m in result.matches)
        assert any(m.type == PIIType.CITY for m in result.matches)
        restored = surrogate.restore(result.text, result.mapping)
        assert "Juan" in restored
        assert "Calle Falsa 123" in restored
        assert "Madrid" in restored


# ===========================================================================
# Configurabilidad
# ===========================================================================


class TestConfiguration:

    def test_env_salt_used_when_no_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PII_SALT", "env-salt-xyz")
        s = PIISurrogate()
        assert s.salt == "env-salt-xyz"

    def test_explicit_salt_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATLAS_PII_SALT", "env-salt")
        s = PIISurrogate(salt="explicit")
        assert s.salt == "explicit"

    def test_enabled_types_filter(self) -> None:
        s = PIISurrogate(salt="x", enabled_types={PIIType.EMAIL})
        matches = s.detect("email a@b.com y DNI 12345678Z")
        assert all(m.type == PIIType.EMAIL for m in matches)

    def test_enabled_types_filter_for_new_types(self) -> None:
        s = PIISurrogate(salt="x", enabled_types={PIIType.NAME})
        matches = s.detect("Mi nombre es Juan y vivo en Madrid")
        assert all(m.type == PIIType.NAME for m in matches)
        assert any(m.original.lower() == "juan" for m in matches)


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:

    def test_overlapping_patterns_resolved(self, surrogate: PIISurrogate) -> None:
        # Una IPv4 dentro de texto largo no debe partir otros tokens
        text = "mira 192.168.1.1 que IP tan curiosa"
        matches = surrogate.detect(text)
        ipv4 = [m for m in matches if m.type == PIIType.IPV4]
        assert len(ipv4) == 1
        assert ipv4[0].original == "192.168.1.1"

    def test_mapping_does_not_grow_with_repeats(
        self, surrogate: PIISurrogate
    ) -> None:
        result = surrogate.redact("ping a@b.com, ping a@b.com, ping a@b.com")
        # Un solo par surrogate->original en mapping aunque haya 3 matches
        assert len(result.mapping) == 1

    def test_restore_empty_mapping_returns_input(
        self, surrogate: PIISurrogate
    ) -> None:
        assert surrogate.restore("hola", {}) == "hola"

    def test_restore_handles_overlapping_surrogates(
        self, surrogate: PIISurrogate
    ) -> None:
        # mapping artificial donde un surrogate corto es prefijo de otro largo
        mapping = {"abc": "X", "abcd": "Y"}
        out = surrogate.restore("token abcd y abc separados", mapping)
        # 'abcd' debe sustituirse primero por ser mas largo
        assert "Y" in out
        assert "X" in out
