"""Tests para VoiceModule (Gate E/E3, ADR-003).

Todos los tests usan mode="stub" — no requieren hardware de audio
ni las deps opcionales (faster-whisper, piper-tts, sounddevice).
"""
from __future__ import annotations

import pytest

from atlas.interfaces.voice import (
    STUB_STT_TEXT,
    STTResult,
    TTSResult,
    VoiceConfig,
    VoiceModule,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def vm_stub() -> VoiceModule:
    return VoiceModule(mode="stub")


@pytest.fixture()
def vm_auto() -> VoiceModule:
    """Auto mode: aterriza en stub si las deps de voz no están instaladas."""
    return VoiceModule(mode="auto")


# ---------------------------------------------------------------------------
# Init y modo
# ---------------------------------------------------------------------------

class TestVoiceModuleInit:
    def test_stub_mode(self, vm_stub: VoiceModule) -> None:
        assert vm_stub.mode == "stub"

    def test_auto_falls_to_stub_without_deps(self, vm_auto: VoiceModule) -> None:
        # En CI / dev sin faster-whisper: auto → stub
        assert vm_auto.mode in ("stub", "real")

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="mode invalido"):
            VoiceModule(mode="invalid")  # type: ignore[arg-type]

    def test_real_mode_raises_without_deps(self) -> None:
        """Si las deps no están, solicitar 'real' lanza RuntimeError."""
        from atlas.interfaces.voice import REAL_DEPS_AVAILABLE
        if not REAL_DEPS_AVAILABLE:
            with pytest.raises(RuntimeError, match="Modo real"):
                VoiceModule(mode="real")

    def test_is_real_false_in_stub(self, vm_stub: VoiceModule) -> None:
        assert vm_stub.is_real is False

    def test_info_dict_keys(self, vm_stub: VoiceModule) -> None:
        info = vm_stub.info()
        assert "mode" in info
        assert "real_deps_available" in info
        assert "whisper_loaded" in info
        assert "piper_loaded" in info
        assert info["mode"] == "stub"

    def test_custom_config(self) -> None:
        cfg = VoiceConfig(whisper_model="tiny", piper_model="es_MX-test")
        vm = VoiceModule(config=cfg, mode="stub")
        assert vm._config.whisper_model == "tiny"


# ---------------------------------------------------------------------------
# STT (stub)
# ---------------------------------------------------------------------------

class TestSTTStub:
    def test_listen_returns_stt_result(self, vm_stub: VoiceModule) -> None:
        result = vm_stub.listen()
        assert isinstance(result, STTResult)

    def test_listen_returns_stub_text(self, vm_stub: VoiceModule) -> None:
        result = vm_stub.listen()
        assert result.text == STUB_STT_TEXT

    def test_listen_mode_is_stub(self, vm_stub: VoiceModule) -> None:
        result = vm_stub.listen()
        assert result.mode == "stub"

    def test_listen_confidence_is_1(self, vm_stub: VoiceModule) -> None:
        result = vm_stub.listen()
        assert result.confidence == 1.0

    def test_listen_latency_positive(self, vm_stub: VoiceModule) -> None:
        result = vm_stub.listen()
        assert result.latency_ms >= 0

    def test_listen_ignores_duration_in_stub(self, vm_stub: VoiceModule) -> None:
        r1 = vm_stub.listen(duration_s=1.0)
        r2 = vm_stub.listen(duration_s=10.0)
        assert r1.text == r2.text

    def test_listen_multiple_calls(self, vm_stub: VoiceModule) -> None:
        results = [vm_stub.listen() for _ in range(3)]
        assert all(r.text == STUB_STT_TEXT for r in results)


# ---------------------------------------------------------------------------
# TTS (stub)
# ---------------------------------------------------------------------------

class TestTTSStub:
    def test_speak_returns_tts_result(self, vm_stub: VoiceModule, capsys) -> None:
        result = vm_stub.speak("Hola Atlas")
        assert isinstance(result, TTSResult)

    def test_speak_mode_is_stub(self, vm_stub: VoiceModule, capsys) -> None:
        result = vm_stub.speak("test")
        assert result.mode == "stub"

    def test_speak_prints_to_stdout(self, vm_stub: VoiceModule, capsys) -> None:
        vm_stub.speak("Mensaje de prueba")
        captured = capsys.readouterr()
        assert "Mensaje de prueba" in captured.out

    def test_speak_text_preserved(self, vm_stub: VoiceModule, capsys) -> None:
        result = vm_stub.speak("Hola mundo")
        assert result.text == "Hola mundo"

    def test_speak_empty_string(self, vm_stub: VoiceModule, capsys) -> None:
        result = vm_stub.speak("")
        assert result.audio_ms == 0
        assert result.latency_ms == 0

    def test_speak_audio_ms_proportional_to_length(self, vm_stub: VoiceModule, capsys) -> None:
        short = vm_stub.speak("Hola")
        long_ = vm_stub.speak("Esta es una frase mucho más larga con muchas palabras adicionales")
        assert long_.audio_ms > short.audio_ms

    def test_speak_latency_positive(self, vm_stub: VoiceModule, capsys) -> None:
        result = vm_stub.speak("prueba")
        assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# Info / estado
# ---------------------------------------------------------------------------

class TestVoiceModuleInfo:
    def test_info_stub_no_models_loaded(self, vm_stub: VoiceModule) -> None:
        info = vm_stub.info()
        assert info["whisper_loaded"] is False
        assert info["piper_loaded"] is False

    def test_info_stub_models_are_none(self, vm_stub: VoiceModule) -> None:
        info = vm_stub.info()
        assert info["whisper_model"] is None
        assert info["piper_model"] is None

    def test_info_keys_complete(self, vm_stub: VoiceModule) -> None:
        info = vm_stub.info()
        expected = {"mode", "real_deps_available", "whisper_model", "piper_model",
                    "whisper_loaded", "piper_loaded", "audio_ok", "whisper_ok", "piper_ok"}
        assert expected.issubset(info.keys())


# ---------------------------------------------------------------------------
# STTResult / TTSResult dataclasses
# ---------------------------------------------------------------------------

class TestResultDataclasses:
    def test_stt_result_fields(self) -> None:
        r = STTResult(text="hola", confidence=0.9, latency_ms=150, mode="stub")
        assert r.text == "hola"
        assert r.confidence == 0.9
        assert r.latency_ms == 150
        assert r.mode == "stub"
        assert r.language == "es"  # default

    def test_tts_result_fields(self) -> None:
        r = TTSResult(text="hola", audio_ms=500, latency_ms=120, mode="stub")
        assert r.text == "hola"
        assert r.audio_ms == 500
        assert r.latency_ms == 120
        assert r.mode == "stub"

    def test_voice_config_defaults(self) -> None:
        cfg = VoiceConfig()
        assert cfg.whisper_model == "small"
        assert cfg.sample_rate == 16000
        assert cfg.max_record_s == 8.0
        assert cfg.piper_model_path is None


# ---------------------------------------------------------------------------
# VoiceConfig
# ---------------------------------------------------------------------------

class TestVoiceConfig:
    def test_custom_whisper_model(self) -> None:
        cfg = VoiceConfig(whisper_model="tiny")
        assert cfg.whisper_model == "tiny"

    def test_custom_sample_rate(self) -> None:
        cfg = VoiceConfig(sample_rate=22050)
        assert cfg.sample_rate == 22050

    def test_piper_model_path_default_none(self) -> None:
        cfg = VoiceConfig()
        assert cfg.piper_model_path is None
