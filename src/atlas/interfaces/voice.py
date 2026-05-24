"""Atlas Core — Módulo de voz (Gate E/E3, ADR-003).

STT: faster-whisper (CPU, modelo small → ~400ms en i7-6700HQ).
TTS: piper-tts (neural CPU, ~150ms por frase).
Audio I/O: sounddevice (portaudio2 ya instalado en sistema).

Modos: stub / real / auto (mismo patrón que InferenceHub).
- stub: listen() devuelve texto fijo; speak() imprime a consola. Sin deps de audio.
- real: faster-whisper + piper + sounddevice. Requiere: pip install atlas[voice].
- auto: intenta real, cae a stub si las deps no están disponibles.

Solo activo en OperationalMode.NORMAL (temp < 70°C, RAM > 1GB libre).
Instalación deps reales: pip install 'atlas-core[voice]'

CLI: atlas voice
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional deps — cargados sólo en modo real
# ---------------------------------------------------------------------------

try:
    import numpy as np
    import sounddevice as sd          # pip install sounddevice
    _AUDIO_OK = True
except ImportError:
    _AUDIO_OK = False
    np = None  # type: ignore[assignment]
    sd = None  # type: ignore[assignment]

try:
    from faster_whisper import WhisperModel   # pip install faster-whisper
    _WHISPER_OK = True
except ImportError:
    _WHISPER_OK = False
    WhisperModel = None  # type: ignore[assignment,misc]

try:
    from piper import PiperVoice              # pip install piper-tts
    _PIPER_OK = True
except ImportError:
    _PIPER_OK = False
    PiperVoice = None  # type: ignore[assignment,misc]

REAL_DEPS_AVAILABLE = _AUDIO_OK and _WHISPER_OK and _PIPER_OK

# ---------------------------------------------------------------------------
# Config & resultado types
# ---------------------------------------------------------------------------

SAMPLE_RATE = 16000       # Hz — requerido por Whisper
CHANNELS    = 1           # mono
DTYPE       = "int16"     # 16-bit signed

STUB_STT_TEXT   = "[STUB] Muéstrame el estado de Atlas"
STUB_TTS_AUDIO_MS = 800  # latencia simulada en stub


@dataclass
class STTResult:
    """Resultado de transcripción de voz."""
    text: str
    confidence: float        # 0.0–1.0 (Whisper avg segment confidence)
    latency_ms: int
    mode: str                # "stub" | "real"
    language: str = "es"


@dataclass
class TTSResult:
    """Resultado de síntesis de voz."""
    text: str
    audio_ms: int            # duración del audio generado
    latency_ms: int
    mode: str                # "stub" | "real"


@dataclass
class VoiceConfig:
    """Configuración del módulo de voz."""
    whisper_model:  str  = "small"                    # tiny|base|small|medium
    whisper_device: str  = "cpu"
    whisper_compute_type: str = "int8"                # int8 más rápido en CPU
    piper_model:    str  = "en_US-ryan-medium"        # voz Piper
    piper_model_path: Path | None = None              # None → descarga automática
    sample_rate:    int  = SAMPLE_RATE
    max_record_s:   float = 8.0                       # máximo de grabación
    silence_threshold_db: float = -40.0               # silencio para parar
    tts_speed:      float = 1.0
    vad_threshold:  float = 0.3                       # 0.0–1.0; default faster-whisper=0.5, 0.3=más sensible


# ---------------------------------------------------------------------------
# VoiceModule
# ---------------------------------------------------------------------------

class VoiceModule:
    """
    STT + TTS para Atlas.
    Modos: stub (sin hardware, para tests) / real (faster-whisper + piper) / auto.

    Uso real:
        vm = VoiceModule(mode="auto")
        result = vm.listen(duration_s=5)
        print(result.text)
        vm.speak("Hola, soy Atlas.")

    Uso stub (tests):
        vm = VoiceModule(mode="stub")
        result = vm.listen()       # devuelve STUB_STT_TEXT
        vm.speak("cualquier texto")  # imprime en consola, no reproduce audio
    """

    def __init__(
        self,
        config: VoiceConfig | None = None,
        mode: str = "auto",
    ) -> None:
        if mode not in ("auto", "real", "stub"):
            raise ValueError(f"mode invalido: {mode!r}. Usa 'auto', 'real' o 'stub'.")

        self._config = config or VoiceConfig()
        self._mode = self._resolve_mode(mode)
        self._whisper: Any = None
        self._piper: Any = None
        self._lock = threading.Lock()

        _log.info("VoiceModule init en modo %s (deps_ok=%s)", self._mode, REAL_DEPS_AVAILABLE)

    # ------------------------------------------------------------------
    # Modo
    # ------------------------------------------------------------------

    def _resolve_mode(self, requested: str) -> str:
        if requested == "stub":
            return "stub"
        if requested == "real":
            if not REAL_DEPS_AVAILABLE:
                missing = []
                if not _AUDIO_OK:
                    missing.append("sounddevice")
                if not _WHISPER_OK:
                    missing.append("faster-whisper")
                if not _PIPER_OK:
                    missing.append("piper-tts")
                raise RuntimeError(
                    f"Modo real solicitado pero faltan deps: {', '.join(missing)}. "
                    "Instala con: pip install 'atlas-core[voice]'"
                )
            return "real"
        # auto
        if REAL_DEPS_AVAILABLE:
            return "real"
        _log.warning(
            "VoiceModule en modo stub — deps de voz no instaladas. "
            "Para audio real: pip install 'atlas-core[voice]'"
        )
        return "stub"

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_real(self) -> bool:
        return self._mode == "real"

    # ------------------------------------------------------------------
    # Lazy init de modelos (sólo en modo real)
    # ------------------------------------------------------------------

    def _get_whisper(self) -> Any:
        if self._whisper is None and self._mode == "real":
            with self._lock:
                if self._whisper is None:
                    # Silenciar warning de HF Hub sobre tokens (no relevante para uso local)
                    os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
                    _log.info("Cargando Whisper modelo '%s'...", self._config.whisper_model)
                    t0 = time.monotonic()
                    self._whisper = WhisperModel(
                        self._config.whisper_model,
                        device=self._config.whisper_device,
                        compute_type=self._config.whisper_compute_type,
                    )
                    ms = int((time.monotonic() - t0) * 1000)
                    _log.info("Whisper listo en %d ms", ms)
        return self._whisper

    def _get_piper(self) -> Any:
        if self._piper is None and self._mode == "real":
            with self._lock:
                if self._piper is None:
                    _log.info("Cargando Piper voz '%s'...", self._config.piper_model)
                    model_path = self._config.piper_model_path
                    if model_path is None:
                        # Piper descarga automáticamente en ~/.local/share/piper
                        self._piper = PiperVoice.load(self._config.piper_model)
                    else:
                        self._piper = PiperVoice.load(str(model_path))
                    _log.info("Piper listo")
        return self._piper

    # ------------------------------------------------------------------
    # STT — escuchar y transcribir
    # ------------------------------------------------------------------

    def listen(self, duration_s: float | None = None) -> STTResult:
        """
        Graba audio del micrófono y transcribe con Whisper.

        En modo stub devuelve STUB_STT_TEXT sin acceder al hardware.
        En modo real graba `duration_s` segundos (o hasta silencio) y transcribe.

        Args:
            duration_s: Duración en segundos. None → usa config.max_record_s.
        """
        if self._mode == "stub":
            return self._listen_stub()
        return self._listen_real(duration_s or self._config.max_record_s)

    def _listen_stub(self) -> STTResult:
        t0 = time.monotonic()
        time.sleep(0.01)  # simula latencia mínima
        return STTResult(
            text=STUB_STT_TEXT,
            confidence=1.0,
            latency_ms=int((time.monotonic() - t0) * 1000),
            mode="stub",
        )

    def _listen_real(self, duration_s: float) -> STTResult:
        whisper = self._get_whisper()
        sr = self._config.sample_rate
        n_samples = int(duration_s * sr)

        _log.debug("Grabando %.1f segundos a %d Hz...", duration_s, sr)
        t0 = time.monotonic()

        audio_int16 = sd.rec(
            n_samples,
            samplerate=sr,
            channels=CHANNELS,
            dtype=DTYPE,
        )
        sd.wait()
        record_ms = int((time.monotonic() - t0) * 1000)

        # Convertir a float32 normalizado para Whisper
        audio_f32 = audio_int16.flatten().astype("float32") / 32768.0

        # Feedback de nivel — avisa si el mic está silencioso
        peak = float(np.abs(audio_int16).max()) / 32768.0
        if peak < 0.005:
            _log.warning("Nivel de audio muy bajo (peak=%.4f) — sube el volumen del micrófono", peak)
        else:
            _log.debug("Nivel de audio: peak=%.3f", peak)

        _log.debug("Transcribiendo %d muestras (vad_threshold=%.2f)...",
                   len(audio_f32), self._config.vad_threshold)
        t1 = time.monotonic()

        def _consume(segs: Any) -> tuple[str, float, int]:
            parts, total_conf, n = [], 0.0, 0
            for seg in segs:
                parts.append(seg.text.strip())
                total_conf += min(1.0, max(0.0, seg.avg_logprob + 1.0))
                n += 1
            txt = " ".join(parts).strip()
            conf = (total_conf / n) if n > 0 else 0.0
            return txt, conf, n

        segments, info = whisper.transcribe(
            audio_f32,
            language="es",
            beam_size=3,
            vad_filter=True,
            vad_parameters={"threshold": self._config.vad_threshold},
        )
        text, confidence, n_seg = _consume(segments)

        # Fallback sin VAD si el filtro descartó todo (threshold demasiado agresivo)
        if n_seg == 0 and peak >= 0.005:
            _log.debug("VAD sin segmentos — reintentando sin vad_filter (peak=%.3f)", peak)
            segments2, info = whisper.transcribe(
                audio_f32,
                language="es",
                beam_size=3,
                vad_filter=False,
            )
            text, confidence, n_seg = _consume(segments2)

        transcribe_ms = int((time.monotonic() - t1) * 1000)
        total_ms = record_ms + transcribe_ms

        _log.info(
            "STT: '%s' (conf=%.2f, %dms grabación + %dms transcripción)",
            text[:60], confidence, record_ms, transcribe_ms,
        )
        return STTResult(
            text=text,
            confidence=confidence,
            latency_ms=total_ms,
            mode="real",
            language=info.language,
        )

    # ------------------------------------------------------------------
    # TTS — sintetizar y reproducir
    # ------------------------------------------------------------------

    def speak(self, text: str) -> TTSResult:
        """
        Sintetiza texto con Piper y lo reproduce por el altavoz.

        En modo stub imprime el texto a consola sin acceder al hardware.
        """
        if not text.strip():
            return TTSResult(text=text, audio_ms=0, latency_ms=0, mode=self._mode)

        if self._mode == "stub":
            return self._speak_stub(text)
        return self._speak_real(text)

    def _speak_stub(self, text: str) -> TTSResult:
        t0 = time.monotonic()
        print(f"[Atlas voz] {text}")
        time.sleep(0.01)
        # Estimación: ~150ms/palabra en TTS real
        audio_ms = int(len(text.split()) * 150)
        return TTSResult(
            text=text,
            audio_ms=audio_ms,
            latency_ms=int((time.monotonic() - t0) * 1000),
            mode="stub",
        )

    def _speak_real(self, text: str) -> TTSResult:
        piper = self._get_piper()
        t0 = time.monotonic()

        # Piper genera wav en memoria; reproducir con sounddevice
        import io
        import wave

        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)       # 16-bit
            wf.setframerate(self._config.sample_rate)
            piper.synthesize(text, wf)

        wav_buf.seek(0)
        with wave.open(wav_buf) as wf:
            n_frames = wf.getnframes()
            audio_ms = int(n_frames / wf.getframerate() * 1000)
            raw = wf.readframes(n_frames)

        audio_np = (
            np.frombuffer(raw, dtype="int16")
            .reshape(-1, CHANNELS)
            .astype("float32") / 32768.0
        )
        synth_ms = int((time.monotonic() - t0) * 1000)

        sd.play(audio_np, samplerate=self._config.sample_rate)
        sd.wait()

        total_ms = int((time.monotonic() - t0) * 1000)
        _log.info("TTS: %d chars → %d ms audio, %d ms latencia", len(text), audio_ms, total_ms)

        return TTSResult(
            text=text,
            audio_ms=audio_ms,
            latency_ms=total_ms,
            mode="real",
        )

    # ------------------------------------------------------------------
    # Loop interactivo
    # ------------------------------------------------------------------

    def run_loop(
        self,
        orchestrator: Any | None = None,
        on_text: Any | None = None,
    ) -> None:
        """
        Loop interactivo: escucha → transcribe → envía a Orchestrator → habla.

        Args:
            orchestrator: Instancia de Orchestrator. Si None, sólo transcribe.
            on_text: Callback opcional (text: str) → str. Si None se usa orchestrator.

        Loop termina con Ctrl+C.
        """
        print(f"[Atlas voz] Módulo activo (modo {self._mode}). Ctrl+C para salir.")
        if self._mode == "stub":
            print("[Atlas voz] Modo stub: cada iteración usa texto fijo.")

        while True:
            try:
                input("\nPresiona Enter para hablar (Ctrl+C para salir)...")
                print("[Atlas voz] Escuchando...")
                stt = self.listen()
                if not stt.text:
                    print("[Atlas voz] No se detectó voz.")
                    continue

                print(f"[Atlas voz] Transcripción: {stt.text!r} ({stt.latency_ms}ms)")

                response = ""
                if on_text is not None:
                    response = on_text(stt.text)
                elif orchestrator is not None:
                    from atlas.core.contracts import Task, TaskSource  # noqa: PLC0415
                    task = Task(intent=stt.text, source=TaskSource.CLI)
                    result = orchestrator.handle_intent(task)
                    response = result.get("output", result.get("message", str(result)))
                else:
                    response = f"(sin orchestrator) Dijiste: {stt.text}"

                if response:
                    tts = self.speak(response)
                    _log.debug("TTS: %d ms", tts.latency_ms)

            except KeyboardInterrupt:
                print("\n[Atlas voz] Deteniendo.")
                break

    # ------------------------------------------------------------------
    # Info
    # ------------------------------------------------------------------

    def info(self) -> dict[str, Any]:
        """Devuelve estado del módulo (útil para dashboard /providers)."""
        return {
            "mode": self._mode,
            "real_deps_available": REAL_DEPS_AVAILABLE,
            "whisper_model": self._config.whisper_model if self._mode == "real" else None,
            "piper_model": self._config.piper_model if self._mode == "real" else None,
            "whisper_loaded": self._whisper is not None,
            "piper_loaded": self._piper is not None,
            "audio_ok": _AUDIO_OK,
            "whisper_ok": _WHISPER_OK,
            "piper_ok": _PIPER_OK,
        }
