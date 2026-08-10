import json
from pathlib import Path
from typing import Any
import pytest

from unittest.mock import MagicMock
from atlas.core.orchestrator import Orchestrator
from atlas.core.contracts import TaskSource, Task
from atlas.core.inference_hub import InferenceRequest

# We need a custom mock for the Inference Hub that will emit our tool calls in sequence
class MockHubForCrossTool:
    def __init__(self):
        self.call_count = 0

    def infer(self, req: InferenceRequest) -> Any:
        from atlas.core.inference_hub import InferenceResponse, InferenceLevel
        
        self.call_count += 1
        if self.call_count == 1:
            return InferenceResponse(
                text="", provider="mock", model="mock", level=InferenceLevel.L1,
                latency_ms=0, success=True,
                tool_calls=[{
                    "name": "browser_navigate",
                    "arguments": json.dumps({"url": "https://example.com"}),
                    "id": "call_1"
                }]
            )
        if self.call_count == 2:
            return InferenceResponse(
                text="", provider="mock", model="mock", level=InferenceLevel.L1,
                latency_ms=0, success=True,
                tool_calls=[{
                    "name": "editor_write",
                    "arguments": json.dumps({"path": "test_script.py", "content": "print('hello from browser')\n"}),
                    "id": "call_2"
                }]
            )
        if self.call_count == 3:
            return InferenceResponse(
                text="", provider="mock", model="mock", level=InferenceLevel.L1,
                latency_ms=0, success=True,
                tool_calls=[{
                    "name": "terminal_plan",
                    "arguments": json.dumps({"instruction": "Run python test_script.py"}),
                    "id": "call_3"
                }]
            )
        
        return InferenceResponse(
            text="Done combining browser, editor, and terminal!",
            provider="mock", model="mock", level=InferenceLevel.L1,
            latency_ms=0, success=True
        )


class DummyBrowser:
    def navigate(self, url: str) -> Any:
        class Result:
            url = url
            title = "Example"
        return Result()

class DummyEditor:
    def write_file(self, path: Path, content: str, clearance: str = None) -> Any:
        path.write_text(content)
        class Result:
            path = str(path)
            size = len(content)
        return Result()

class DummyTerminalPlanner:
    def plan(self, instruction: str, obs: str) -> Any:
        class Step:
            kind = "stop"
            reason = f"Simulated stop for {instruction}"
            script = None
        return Step()

@pytest.fixture
def fake_orch(tmp_path: Path) -> Orchestrator:
    o = Orchestrator(workspace=tmp_path)
    # Enable Gate D pipeline so we use AgenticExecutor for LOCAL_SAFE tasks
    o.enable_gate_d_pipeline()
    o._inference_hub = MockHubForCrossTool()
    
    # We must auto-approve the mutations so the loop doesn't suspend
    o.set_agentic_auto_approve(["browser_navigate", "editor_write", "terminal_plan"])
    
    # Mock Gate F tools so they don't actually run real tools
    o._gate_f_exec.attach(
        browser=DummyBrowser(),
        editor=DummyEditor(),
        terminal_planner=DummyTerminalPlanner()
    )
    return o


def test_t3_4_cross_tool_orchestration(fake_orch: Orchestrator, tmp_path: Path):
    """
    Test T3.4: El Orchestrator debe transicionar fluidamente entre Browser, Editor y Terminal
    usando el loop agéntico, si las mutaciones son aprobadas.
    """
    from atlas.router.classifier import ClassificationResult
    from atlas.core.contracts import RoutingLevel
    
    # Force _hybrid.classify to return LOCAL_SAFE so it goes to AgenticExecutor
    fake_orch._hybrid.classify = MagicMock(return_value=ClassificationResult(
        level=RoutingLevel.LOCAL_SAFE,
        reason="Test fallback to agentic",
        confidence=1.0,
        matched_pattern="fallback",
        governance_blocked=False
    ))
    
    task = fake_orch.handle_intent("Lee una web, escribe su contenido en un fichero y ejecutalo", TaskSource.CLI)
    
    # Let's verify the result of the task
    assert "Done combining browser, editor, and terminal!" in str(task.result)
    
    # Verify editor_write actually happened
    script = tmp_path / "test_script.py"
    assert script.exists()
    assert script.read_text() == "print('hello from browser')\n"
