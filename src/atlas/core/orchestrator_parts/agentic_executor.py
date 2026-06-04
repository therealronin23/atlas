"""Núcleo de ejecución agéntico — extraído de ``Orchestrator`` (sesión dedicada).

Front-half de la decomposición del god-object cerró su fase mecánica; esto es la
pieza marcada como **alto riesgo**: el loop de tool-calls (ADR-031) con
suspensión/reanudación HITL (ADR-032/033) y la frontera de contenido no confiable
(ADR-037). Es un único núcleo *mutuamente recursivo* (``drive`` ↔ ``resume`` ↔
``_suspend`` ↔ dispatch), no varios colaboradores separables.

Extracción **bit-a-bit**: los métodos se movieron sin cambiar su lógica. El
executor guarda una referencia al ``Orchestrator`` (``host``) y lee sus
colaboradores **en tiempo de llamada**, no en el constructor — eso preserva la
conducta de los tests que swappean ``host._mcp`` o ajustan
``host._agentic_auto_approve`` tras construir el Orchestrator. Los helpers puros y
los predicados testeados (``_agentic_tool_*``, ``_wrap_untrusted``,
``_is_agentic_auto_approved``, ``sweep_expired_suspensions``) se quedan en el host
y se invocan vía ``self._host``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from atlas.core.contracts import EventType, RoutingLevel, Task, TaskStatus
from atlas.core.decider import Allow, DecisionAction, Deny, RequiresHuman
from atlas.memory.block_memory import (
    BlockLimitExceeded,
    BlockMemoryError,
    BlockNotFound,
)

if TYPE_CHECKING:
    from atlas.core.orchestrator import Orchestrator


class AgenticExecutor:
    """Loop agéntico suspendible (ADR-031/032/033/037). Lee colaboradores del
    ``Orchestrator`` host en tiempo de llamada para conservar paridad exacta."""

    def __init__(self, host: "Orchestrator") -> None:
        self._host = host

    def execute_local_safe(self, task: Task) -> None:
        """
        Ejecuta una tarea LOCAL_SAFE invocando al InferenceHub.

        Pipeline:
          1. PIISurrogate.redact sobre el intent (no salen datos sensibles).
          2. MemoryDistiller.build_context para curar el contexto del prompt
             si hay vector_store conectado (sin vector_store cae a system+intent).
          3. PIISurrogate.redact tambien sobre el contexto.
          4. InferenceHub.infer con prompt + context redactados.
          5. PIISurrogate.restore sobre el texto de respuesta.
          6. Si la inferencia falla, fallback a passthrough con error.

        El resultado se guarda en task.result con la respuesta restaurada y
        metadatos del proveedor (provider, model, latency, tokens).
        """
        host = self._host
        thermal_policy = host._thermal_blocks_local_llm()
        if thermal_policy:
            task.tool_name = "local_safe.thermal_blocked"
            task.result = {
                "error": thermal_policy,
                "message": "Inferencia local pausada por modo termico (DEGRADED/OMEGA).",
                "thermal": True,
            }
            return

        # Lazy imports para evitar cargar litellm si nadie usa esto
        from atlas.core.inference_hub import InferenceLevel, InferenceRequest
        from atlas.memory.distiller import ChunkSource

        # 1. Redact intent
        redacted_intent = host._pii_surrogate.redact(task.intent)

        # 2. Distill context. Sin vector_store, gather_relevant devuelve [];
        # el contexto sera basicamente el system context (si esta cargado).
        system_text = ""
        if host._system_context is not None:
            system_text = host._system_context.as_system_context()
        if host._distiller is not None and system_text:
            ctx_text, _ = host._distiller.build_context(
                query=task.intent,
                system_chunks=[system_text] if system_text else None,
            )
        else:
            ctx_text = system_text

        # 2b. ADR-030: bloques de core memory siempre-en-contexto, antes del
        # contexto archival. Vacio si no hay bloques (no inyecta nada).
        blocks_text = host._block_memory.render()
        if blocks_text:
            ctx_text = f"{blocks_text}\n\n{ctx_text}" if ctx_text else blocks_text

        # 3. Redact context
        redacted_ctx = host._pii_surrogate.redact(ctx_text)

        # 4. Inference call. ADR-031: exponemos herramientas de grounding al
        # modelo. La PRIMERA llamada usa prompt+context (idéntico a v0.x: si el
        # modelo no pide tools, una sola iteración → comportamiento previo).
        tool_specs = host._agentic_tool_specs()
        request = InferenceRequest(
            prompt=redacted_intent.text,
            level=InferenceLevel.L1,
            context=redacted_ctx.text,
            max_tokens=512,
            temperature=0.3,
            task_id=task.id,
            tools=tool_specs,
        )
        response = host._inference_hub.infer(request)

        if not response.success:
            self._record_inference_failure(task, response)
            return

        # ADR-031: loop agéntico. Si el modelo pidió herramientas, las ejecutamos
        # (auditadas), reinyectamos resultados y volvemos a llamar hasta respuesta
        # final o tope de iteraciones. Las preguntas factuales se contestan con
        # datos reales (git, fs, blocks) en vez de alucinarse.
        iterations = 0
        tools_used: list[str] = []
        if response.tool_calls:
            messages: list[dict[str, Any]] = []
            if redacted_ctx.text:
                messages.append({"role": "system", "content": redacted_ctx.text})
            messages.append({"role": "user", "content": redacted_intent.text})

            # ADR-032: el loop puede suspenderse si el modelo pide una mutación
            # de host (browser/editor). En ese caso drive devuelve
            # None tras dejar la tarea AWAITING_APPROVAL; reanudaremos en
            # approve_pending. Si termina, devuelve (response, iterations).
            loop_result = self.drive(
                task, messages, response, tool_specs, iterations, tools_used,
            )
            if loop_result is None:
                return
            response, iterations = loop_result

        # 5. Restore PII en la respuesta usando ambos mappings
        combined: dict[str, str] = {}
        combined.update(redacted_intent.mapping)
        combined.update(redacted_ctx.mapping)
        restored = host._pii_surrogate.restore(response.text, combined)

        task.tool_name = "inference_hub.complete"
        task.result = {
            "text":         restored,
            "provider":     response.provider,
            "model":        response.model,
            "latency_ms":   response.latency_ms,
            "tokens_used":  response.tokens_used,
            "mode":         response.mode,
            "pii_redacted": len(redacted_intent.matches) + len(redacted_ctx.matches),
            "iterations":   iterations,
            "tools_used":   tools_used,
        }
        host._merkle.log(
            action="inference.completed",
            agent="orchestrator",
            result="success",
            risk_level="safe",
            payload={
                "provider":     response.provider,
                "model":        response.model,
                "latency_ms":   response.latency_ms,
                "tokens_used":  response.tokens_used,
                "pii_redacted": len(redacted_intent.matches) + len(redacted_ctx.matches),
                "iterations":   iterations,
                "tools_used":   tools_used,
            },
            task_id=task.id,
        )

    def _record_inference_failure(self, task: Task, response: Any) -> None:
        host = self._host
        task.tool_name = "inference_hub.failed"
        task.result = {
            "message": f"InferenceHub no devolvio respuesta: {response.error}",
            "provider": response.provider,
            "intent":   task.intent,
        }
        host._merkle.log(
            action="inference.failed",
            agent="orchestrator",
            result="failure",
            risk_level="moderate",
            payload={"provider": response.provider, "error": response.error},
            task_id=task.id,
        )

    def _emit_progress(
        self, task: Task, iteration: int, tool: str, result: str,
    ) -> None:
        """ADR-033 #4: publica una traza de progreso por iteración del loop para
        que dashboard/Telegram puedan seguir el razonamiento en vivo."""
        self._host._bus.publish_type(EventType.AGENTIC_PROGRESS, {
            "task_id": task.id,
            "iteration": iteration,
            "tool": tool,
            "summary": (result or "")[:200],
        }, task.id)

    def _run_auto_approved_mutation(self, tc: dict[str, Any], task: Task) -> str:
        """Ejecuta una mutación auto-aprobada con clearance concedido al vuelo.
        Audita `task.auto_approved` para que no haya ejecución silenciosa."""
        host = self._host
        host._merkle.log(
            action="task.auto_approved",
            agent="orchestrator.agentic",
            result="approved",
            risk_level="high",
            payload={"tool": tc["name"], "auto": True},
            task_id=task.id,
        )
        host._permissions.mark_confirmed(f"task:{task.id}")
        return self._dispatch_mutation(tc["name"], tc["arguments"], task)

    def _dispatch_tool(
        self, name: str, arguments: str, task: Task
    ) -> str:
        """Ejecuta una herramienta pedida por el modelo y devuelve su resultado
        como texto. Cada invocación se audita. Los errores (incl. límite de
        bloque excedido = presión MemGPT) se devuelven como texto para que el
        modelo reaccione, no como excepción."""
        host = self._host
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}

        host._merkle.log(
            action="tool.invoked",
            agent="orchestrator.agentic",
            result="ok",
            risk_level="safe",
            payload={"tool": name},
            task_id=task.id,
        )

        try:
            if name == "git_log":
                return host._stringify_tool_result(host._run_git_log(task))
            if name == "git_status":
                return host._stringify_tool_result(host._run_git_status(task))
            if name == "git_diff":
                return host._stringify_tool_result(host._run_git_diff(task))
            if name == "list_workspace":
                return host._stringify_tool_result(host._list_workspace())
            if name == "atlas_status":
                return host._stringify_tool_result(host.status().__dict__)
            if name == "read_memory_blocks":
                return host._block_memory.render() or "(sin bloques de memoria)"
            if name == "edit_memory_block":
                block = host._block_memory.set(args["label"], args["value"])
                return f"ok: bloque '{block.label}' actualizado ({block.chars} chars)"
            if name == "append_memory_block":
                block = host._block_memory.append(args["label"], args["text"])
                return f"ok: bloque '{block.label}' ampliado ({block.chars} chars)"
            # ADR-035: tools de servers MCP.
            if name.startswith("mcp__") and host._mcp.knows(name):
                return host._mcp.dispatch(name, args)
            return f"error: herramienta desconocida '{name}'"
        except BlockLimitExceeded as exc:
            return f"error: límite del bloque excedido — resume o acorta el contenido. {exc}"
        except (BlockNotFound, BlockMemoryError) as exc:
            return f"error: {exc}"
        except KeyError as exc:
            return f"error: falta argumento {exc}"
        except Exception as exc:  # noqa: BLE001 — devolvemos el error al modelo
            return f"error: {type(exc).__name__}: {exc}"

    def drive(
        self,
        task: Task,
        messages: list[dict[str, Any]],
        response: Any,
        tool_specs: list[dict[str, Any]],
        iterations: int,
        tools_used: list[str],
    ) -> tuple[Any, int] | None:
        """Maneja el loop agéntico (ADR-031) con suspensión por mutación (ADR-032).

        Las herramientas de lectura corren inline; si el modelo pide una o más
        herramientas mutantes en un turno, se agrupan, el loop se SUSPENDE
        (AWAITING_APPROVAL, estado persistido) y devuelve None. Si el loop
        termina con normalidad devuelve (response_final, iterations). Si la
        inferencia falla, registra el fallo y devuelve None.

        El presupuesto `max_iters` cuenta a través de suspensiones: `iterations`
        entra con el valor acumulado y persiste en el estado serializado.
        """
        host = self._host
        from atlas.core.inference_hub import InferenceLevel, InferenceRequest

        max_iters = 5
        while response.tool_calls and iterations < max_iters:
            iterations += 1
            messages.append({
                "role": "assistant",
                "content": response.text or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in response.tool_calls
                ],
            })
            # ADR-037 patrón #2: si ya se ingirió contenido no confiable en
            # turnos previos, la allowlist de auto-aprobación queda anulada →
            # toda mutación cae a HITL (post-ingestion tool policy).
            tainted = host._loop_is_tainted(messages)
            pending_mutations: list[dict[str, Any]] = []
            for tc in response.tool_calls:
                tools_used.append(tc["name"])
                if host._agentic_tool_kind(tc["name"]) == "mutate":
                    # ADR-040 slice 2: la decisión "¿esta mutación necesita
                    # humano?" pasa por el seam. requires_approval = NO está
                    # auto-aprobada (allowlist ADR-033 + sin taint ADR-037), que
                    # es exactamente la condición que hoy fuerza HITL. Con el
                    # HumanDecider esto reproduce la conducta previa bit a bit.
                    auto_ok = (
                        host._is_agentic_auto_approved(tc["name"], task)
                        and not tainted
                    )
                    verdict, _ = host._consult_decider(
                        DecisionAction(
                            kind="agentic_tool",
                            requires_approval=not auto_ok,
                            mutating=True,
                            descriptor=tc["name"],
                        ),
                        task,
                    )
                    if isinstance(verdict, RequiresHuman):
                        # ADR-032 dec.5: agrupar las mutaciones que SÍ requieren
                        # HITL; no se ejecutan aún, se persiste el tool_call.
                        pending_mutations.append({
                            "id": tc["id"],
                            "name": tc["name"],
                            "arguments": tc["arguments"],
                        })
                        continue
                    if isinstance(verdict, Deny):
                        # El decisor rechaza la mutación: no se ejecuta y se
                        # devuelve el motivo al modelo para que re-planifique.
                        raw_result = (
                            f"error: decisor denegó la mutación '{tc['name']}'"
                            f": {verdict.reason}"
                        )
                    else:
                        # Allow: mutación auto-aprobada (ADR-033 #2) o autorizada
                        # por el decisor → corre inline con clearance, auditada.
                        raw_result = self._run_auto_approved_mutation(tc, task)
                else:
                    raw_result = self._dispatch_tool(
                        tc["name"], tc["arguments"], task
                    )
                # Redactar PII del resultado antes de devolverlo al modelo.
                safe_result = host._pii_surrogate.redact(raw_result).text
                # ADR-037: envolver TODO resultado de fuente no confiable según
                # provenance, no kind. Una tool MCP mutante (ADR-035 mutate-by-
                # default) también devuelve datos externos manipulables;
                # clasificarla 'mutate' no la hace confiable. Cualquier ingesta
                # untrusted marca el loop como tainted para el siguiente turno.
                if host._agentic_tool_provenance(tc["name"]) == "untrusted":
                    safe_result = host._wrap_untrusted(safe_result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": safe_result,
                })
                self._emit_progress(task, iterations, tc["name"], safe_result)

            if pending_mutations:
                self._suspend(
                    task, messages, iterations, tools_used, pending_mutations,
                )
                return None

            request = InferenceRequest(
                prompt="",
                level=InferenceLevel.L1,
                messages=messages,
                tools=tool_specs,
                max_tokens=512,
                temperature=0.3,
                task_id=task.id,
            )
            response = host._inference_hub.infer(request)
            if not response.success:
                self._record_inference_failure(task, response)
                return None

        return response, iterations

    def _suspend(
        self,
        task: Task,
        messages: list[dict[str, Any]],
        iterations: int,
        tools_used: list[str],
        pending_mutations: list[dict[str, Any]],
    ) -> None:
        """ADR-032: serializa el estado del loop y deja la tarea AWAITING_APPROVAL.

        El `messages` array ES la memoria del loop (dec.3). Se persiste en el
        registro de pending approval existente bajo `agentic_state` (dec.4); ya
        viene redactado de PII (los tool results se redactan antes de añadirse),
        así que no persistimos PII en claro. La reanudación ocurre en
        approve_pending al detectar `agentic_state`.
        """
        host = self._host
        names = [m["name"] for m in pending_mutations]
        reason = (
            f"El razonamiento agéntico requiere ejecutar {len(names)} "
            f"mutación(es) de host: {', '.join(names)}"
        )
        task.metadata["agentic_state"] = {
            "messages": messages,
            "iterations": iterations,
            "tools_used": tools_used,
            "pending_mutations": pending_mutations,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        task.route = RoutingLevel.REQUIRES_APPROVAL
        task.tool_name = names[0] if names else "agentic.mutation"
        task.transition(TaskStatus.AWAITING_APPROVAL)
        task.result = {
            "message": "Loop agéntico suspendido; mutaciones requieren aprobación inline.",
            "approved": False,
            "reason": reason,
            "pending_mutations": names,
            "iterations": iterations,
        }
        host._approvals.register(task)
        host._persist_pending_approval(task)
        host._merkle.log(
            action="task.suspended",
            agent="orchestrator.agentic",
            result="pending",
            risk_level="high",
            payload={"iterations": iterations, "pending_mutations": names},
            task_id=task.id,
        )
        host._bus.publish_type(EventType.APPROVAL_REQUIRED, {
            "task_id": task.id,
            "intent": task.intent,
            "reason": reason,
            "tool": task.tool_name,
            # ADR-033: el lote de mutaciones, para que Telegram pueda ofrecer
            # botones de aprobación parcial (uno por mutación) además del lote.
            "pending_mutations": [
                {"id": m.get("id"), "name": m.get("name")}
                for m in pending_mutations
            ],
        }, task.id)

    def _dispatch_mutation(
        self, name: str, arguments: str, task: Task
    ) -> str:
        """ADR-032: ejecuta una mutación de host APROBADA por la vía Gate F, con
        el clearance ya concedido (mark_confirmed("task:<id>") en approve). El
        AtlasExecutor sigue siendo el único que autoriza (dec.8). Devuelve el
        resultado como texto para reinyectarlo al loop."""
        host = self._host
        try:
            args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}

        tool, _, action = name.partition("_")
        host._merkle.log(
            action="tool.invoked",
            agent=f"orchestrator.agentic.{name}",
            result="ok",
            risk_level="high",
            payload={"tool": name},
            task_id=task.id,
        )
        try:
            # ADR-035: mutaciones MCP (mutate-by-default) ejecutan vía registry
            # tras la aprobación HITL/auto. Sin esta ruta, una tool MCP mutante
            # aprobada nunca correría (partition('_') la mandaría a 'mcp').
            if name.startswith("mcp__") and host._mcp.knows(name):
                return host._mcp.dispatch(name, args)
            if tool == "editor":
                result = host._execute_editor_command(action, args, task=task)
            elif tool == "browser":
                result = host._execute_browser_command(action, args)
            else:
                return f"error: mutación desconocida '{name}'"
            return host._stringify_tool_result(result)
        except KeyError as exc:
            return f"error: falta argumento {exc}"
        except Exception as exc:  # noqa: BLE001 — devolvemos el error al modelo
            return f"error: {type(exc).__name__}: {exc}"

    def resume(self, task: Task) -> None:
        """ADR-032: reanuda un loop suspendido. Ejecuta las mutaciones pendientes
        (o inyecta denegación sintética si el humano las rechazó sin abortar),
        reinyecta los resultados y continúa el loop hasta respuesta final o nueva
        suspensión. `iterations` continúa desde el valor persistido (dec.9)."""
        host = self._host
        from atlas.core.inference_hub import InferenceLevel, InferenceRequest

        state = task.metadata.get("agentic_state")
        if not isinstance(state, dict):
            raise RuntimeError("agentic_state ausente o inválido en resume")

        messages = list(state.get("messages") or [])
        iterations = int(state.get("iterations", 0))
        tools_used = list(state.get("tools_used") or [])
        pending_mutations = list(state.get("pending_mutations") or [])
        denied = bool(state.get("denied"))
        deny_reason = str(state.get("deny_reason", "human"))
        # ADR-033 #3: aprobación parcial. Si está presente, solo estas ids se
        # ejecutan; el resto del lote recibe denegación sintética. None → lote
        # entero (compat ADR-032).
        approve_only = state.get("approve_only")
        approved_ids: set[str] | None = (
            set(approve_only) if isinstance(approve_only, list) else None
        )

        # Limpiar el estado para no re-resumir por accidente; si el loop vuelve a
        # suspender, _suspend escribe un agentic_state nuevo.
        task.metadata.pop("agentic_state", None)

        for mut in pending_mutations:
            mut_denied = denied or (
                approved_ids is not None and mut["id"] not in approved_ids
            )
            if mut_denied:
                # dec.6: presión MemGPT — el modelo re-planifica, no crashea.
                reason = deny_reason if denied else "human_partial"
                safe_result = json.dumps(
                    {"denied": True, "reason": reason}, ensure_ascii=False
                )
            else:
                raw_result = self._dispatch_mutation(
                    mut["name"], str(mut.get("arguments", "")), task
                )
                safe_result = host._pii_surrogate.redact(raw_result).text
                # ADR-037: una mutación MCP aprobada por HITL devuelve datos
                # externos no confiables; envolver para que tainte el loop tras
                # la reanudación (mismo criterio provenance que la ruta inline).
                if host._agentic_tool_provenance(mut["name"]) == "untrusted":
                    safe_result = host._wrap_untrusted(safe_result)
            messages.append({
                "role": "tool",
                "tool_call_id": mut["id"],
                "content": safe_result,
            })
            self._emit_progress(task, iterations, mut["name"], safe_result)

        tool_specs = host._agentic_tool_specs()
        request = InferenceRequest(
            prompt="",
            level=InferenceLevel.L1,
            messages=messages,
            tools=tool_specs,
            max_tokens=512,
            temperature=0.3,
            task_id=task.id,
        )
        response = host._inference_hub.infer(request)
        if not response.success:
            self._record_inference_failure(task, response)
            return

        loop_result = self.drive(
            task, messages, response, tool_specs, iterations, tools_used,
        )
        if loop_result is None:
            return  # re-suspendido (nueva aprobación) o fallo ya registrado
        response, iterations = loop_result

        # PII: no persistimos el combined mapping (evitar PII en disco), así que
        # los surrogates no se restauran tras una suspensión (documentado en ADR).
        restored = host._pii_surrogate.restore(response.text, {})
        task.tool_name = "inference_hub.complete"
        task.result = {
            "text":        restored,
            "provider":    response.provider,
            "model":       response.model,
            "latency_ms":  response.latency_ms,
            "tokens_used": response.tokens_used,
            "mode":        response.mode,
            "iterations":  iterations,
            "tools_used":  tools_used,
            "resumed":     True,
            "denied":      denied,
        }
        host._merkle.log(
            action="inference.completed",
            agent="orchestrator",
            result="success",
            risk_level="safe",
            payload={
                "provider":   response.provider,
                "model":      response.model,
                "iterations": iterations,
                "tools_used": tools_used,
                "resumed":    True,
            },
            task_id=task.id,
        )
        task.transition(TaskStatus.DONE)
        host._bus.publish_type(EventType.TASK_COMPLETED, {"task_id": task.id}, task.id)
