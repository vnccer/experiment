import pytest

from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline
from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
from agentdojo.task_suite import get_suite
from agentdojo.types import ChatAssistantMessage
from examples.campus_security import benchmark
from examples.campus_security.pipeline import CheckedToolsExecutor, ScriptedLLM, build_pipeline
from examples.campus_security.runtime import CampusRuntime
from examples.campus_security.tasks import EVENT_ID, EVIDENCE_ID, SOURCE_IP, task_suite


@pytest.mark.parametrize("task_id,count", [("user_task_0", 2), ("user_task_1", 3)])
def test_native_suite_pipeline_and_ground_truth(task_id, count):
    task = task_suite.get_user_task_by_id(task_id)
    assert task_suite.run_task_with_pipeline(GroundTruthPipeline(task), task, None, {}, runtime_class=CampusRuntime)[0]
    env = task_suite.load_and_inject_default_environment({})
    pipeline, tracked = build_pipeline(ScriptedLLM())
    assert task_suite.run_task_with_pipeline(pipeline, task, None, {}, environment=env)[0]
    assert len(env.sandbox.executed_actions) == count
    assert tracked.calls == count + 1
    assert not tracked.messages[-1]["tool_calls"]


def test_registration_and_native_suite_check():
    assert get_suite(benchmark.benchmark_version, "campus_security") is task_suite
    assert task_suite.check(check_injectable=False)[0]


def test_batch_checks_sequential_state_and_keeps_call_ids():
    env = task_suite.get_user_task_by_id("user_task_1").init_environment(
        task_suite.load_and_inject_default_environment({})
    )
    calls = [
        FunctionCall(function="read_event", args={"event_id": EVENT_ID}, id="1"),
        FunctionCall(function="block_ip", args={"ip": SOURCE_IP}, id="2"),
        FunctionCall(
            function="submit_report",
            args={"event_id": EVENT_ID, "verdict": "attack", "evidence_ids": [EVIDENCE_ID]},
            id="3",
        ),
        FunctionCall(function="block_ip", args={"ip": SOURCE_IP}, id="4"),
        FunctionCall(function="unknown", args={}, id="5"),
    ]
    message = ChatAssistantMessage(role="assistant", content=None, tool_calls=calls)
    result = CheckedToolsExecutor().query("", FunctionsRuntime(task_suite.tools), env, [message])
    assert [m["tool_call_id"] for m in result[3][1:]] == ["1", "2", "3", "4", "5"]
    assert [bool(m["error"]) for m in result[3][1:]] == [False, True, False, False, True]
    assert result[3][0] == message
    assert env.sandbox.blocked_ips == [SOURCE_IP]
    assert len(env.sandbox.proposed_actions) == 5
    assert len(env.sandbox.rejected_actions) == 2


def test_reset_between_tasks_and_wrong_verdict_fails_evaluation():
    env = task_suite.load_and_inject_default_environment({})
    task_b = task_suite.get_user_task_by_id("user_task_1")
    pipeline, _ = build_pipeline(ScriptedLLM())
    assert task_suite.run_task_with_pipeline(pipeline, task_b, None, {}, environment=env)[0]
    env.sandbox.reports[EVENT_ID].verdict = "benign"
    assert not task_b.utility("", env, env)
    task_suite.get_user_task_by_id("user_task_0").init_environment(env)
    assert not env.sandbox.reports and not env.sandbox.blocked_ips and not env.sandbox.proposed_actions
