import json

import pytest

from agentdojo.functions_runtime import FunctionCall
from agentdojo.types import ChatAssistantMessage
from examples.campus_security.pipeline import ScriptedLLM
from examples.campus_security.run import make_llm, run_task


@pytest.mark.parametrize("task_id,count", [("A", 2), ("B", 3)])
def test_result_record_and_no_overwrite(tmp_path, task_id, count):
    result, path = run_task(task_id, ScriptedLLM(), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == result
    assert result["task_success"] and result["final_verdict"] == "attack"
    assert result["tool_call_count"] == count
    assert len(result["proposed_actions"]) == len(result["executed_actions"]) == count
    assert not result["is_real_llm"] and not result["unauthorized_action_attempt"]
    assert result["elapsed_time"] >= 0 and result["token_usage"] is None
    assert run_task(task_id, ScriptedLLM(), tmp_path)[1] != path


class BadLLM:
    def query(self, query, runtime, env, messages, extra_args):
        if messages[-1]["role"] == "tool":
            message = ChatAssistantMessage(
                role="assistant", content=[{"type": "text", "content": "done"}], tool_calls=None
            )
        else:
            message = ChatAssistantMessage(
                role="assistant",
                content=None,
                tool_calls=[FunctionCall(function="isolate_host", args={"host": "campus-web-demo"}, id="bad")],
            )
        return query, runtime, env, [*messages, message], extra_args


def test_rejected_actions_are_not_executions(tmp_path):
    result, _ = run_task("A", BadLLM(), tmp_path)
    assert result["unauthorized_action_attempt"] and not result["task_success"]
    assert len(result["proposed_actions"]) == len(result["rejected_actions"]) == 1
    assert not result["executed_actions"] and not result["sandbox_state"]["isolated_hosts"]


def test_iteration_limit_keeps_unexecuted_proposals(tmp_path):
    result, _ = run_task("B", ScriptedLLM(), tmp_path, max_iters=1)
    assert result["run_status"] == "iteration_limit" and not result["task_success"]
    assert len(result["proposed_actions"]) == 2 and len(result["executed_actions"]) == 1
    assert not result["sandbox_state"]["blocked_ips"]


def test_model_error_still_writes_record_without_exception_secrets(tmp_path):
    class FailingLLM:
        def query(self, *args):
            raise RuntimeError("secret-placeholder-must-not-be-written")

    result, path = run_task("A", FailingLLM(), tmp_path)
    assert result["run_status"] == "error" and not result["task_success"]
    assert result["error_type"] == "RuntimeError"
    assert "secret-placeholder" not in path.read_text(encoding="utf-8")


def test_missing_credentials_is_explicit(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_AUTH_TOKEN"):
        make_llm("anthropic", "example-model")


def test_none_content_at_limit_does_not_restart_suite(tmp_path):
    class NeverFinishes:
        def query(self, query, runtime, env, messages, extra_args):
            message = ChatAssistantMessage(
                role="assistant",
                content=None,
                tool_calls=[FunctionCall(function="read_event", args={"event_id": "web-001"}, id="repeat")],
            )
            return query, runtime, env, [*messages, message], extra_args

    result, _ = run_task("A", NeverFinishes(), tmp_path, max_iters=1)
    assert result["run_status"] == "iteration_limit"
    assert result["llm_call_count"] == 2
    assert len(result["proposed_actions"]) == 2 and len(result["executed_actions"]) == 1
