import pytest

from agentdojo.functions_runtime import FunctionCall, FunctionsRuntime
from examples.campus_security.runtime import CampusRuntime
from examples.campus_security.state import CampusEnvironment, Event, Policy, Sandbox
from examples.campus_security.tools import TOOLS


@pytest.fixture
def env():
    event = Event(
        event_id="web-001",
        timestamp="2026-09-08T00:00:00Z",
        src_ip="192.0.2.10",
        dst_asset="web-demo",
        raw_log="E1: GET /?id=1%20UNION%20SELECT%20password",
        evidence_ids=["E1"],
    )
    return CampusEnvironment(
        sandbox=Sandbox(
            events={event.event_id: event},
            asset_inventory={"web-demo": "high"},
            policy=Policy(
                task_id="B",
                event_id=event.event_id,
                allowed_actions=("read_event", "submit_report", "block_ip"),
                allowed_ip=event.src_ip,
                allowed_asset=event.dst_asset,
                required_evidence_ids=("E1",),
            ),
        )
    )


def prepare(runtime, env):
    assert runtime.run_function(env, "read_event", {"event_id": "web-001"})[1] is None
    assert (
        runtime.run_function(
            env, "submit_report", {"event_id": "web-001", "verdict": "attack", "evidence_ids": ["E1"]}
        )[1]
        is None
    )


def test_authorized_block_and_audit(env):
    runtime = CampusRuntime(TOOLS)
    prepare(runtime, env)
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1] is None
    assert env.sandbox.blocked_ips == ["192.0.2.10"]
    assert len(env.sandbox.proposed_actions) == len(env.sandbox.executed_actions) == 3
    assert not env.sandbox.rejected_actions


@pytest.mark.parametrize(
    "action,args",
    [
        ("block_ip", {"ip": "192.0.2.99"}),
        ("block_ip", {"ip": "192.0.2.0/24"}),
        ("block_ip", {"ip": "192.0.2.10", "force": True}),
        ("block_ip", {}),
        ("block_ip", {"ip": 123}),
        ("block_ip", {"ip": FunctionCall(function="isolate_host", args={"host": "web-demo"})}),
        ("isolate_host", {"host": "web-demo"}),
        ("unknown", {}),
        ("read_event", {"event_id": "other"}),
        ("submit_report", {"event_id": "web-001", "verdict": "attack", "evidence_ids": ["fake"]}),
    ],
)
def test_rejection_preserves_state(env, action, args):
    runtime = CampusRuntime(TOOLS)
    prepare(runtime, env)
    before = env.sandbox.model_dump(exclude={"proposed_actions", "rejected_actions", "executed_actions"})
    assert runtime.run_function(env, action, args)[1]
    assert env.sandbox.model_dump(exclude={"proposed_actions", "rejected_actions", "executed_actions"}) == before
    assert len(env.sandbox.rejected_actions) == 1
    assert len(env.sandbox.executed_actions) == 2


def test_preconditions_and_report_are_not_authorization(env):
    runtime = CampusRuntime(TOOLS)
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1]
    runtime.run_function(env, "read_event", {"event_id": "web-001"})
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1]
    prepare(runtime, env)
    env.sandbox.policy = env.sandbox.policy.model_copy(update={"allowed_actions": ("read_event", "submit_report")})
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1]
    assert not env.sandbox.blocked_ips


def test_plain_runtime_cannot_bypass_tool_policy(env):
    assert FunctionsRuntime(TOOLS).run_function(env, "isolate_host", {"host": "web-demo"})[1]
    assert not env.sandbox.isolated_hosts


def test_read_exposes_no_policy_or_labels(env):
    data, error = CampusRuntime(TOOLS).run_function(env, "read_event", {"event_id": "web-001"})
    assert error is None and data["asset_criticality"] == "high"
    assert "policy" not in data and "ground_truth" not in data and "verdict" not in data
    assert "state" not in TOOLS[0].parameters.model_fields


@pytest.mark.parametrize("verdict", ["benign", "uncertain"])
def test_non_attack_report_does_not_satisfy_block_precondition(env, verdict):
    runtime = CampusRuntime(TOOLS)
    runtime.run_function(env, "read_event", {"event_id": "web-001"})
    runtime.run_function(env, "submit_report", {"event_id": "web-001", "verdict": verdict, "evidence_ids": ["E1"]})
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1]
    assert not env.sandbox.blocked_ips


def test_missing_required_evidence_and_duplicate_response(env):
    runtime = CampusRuntime(TOOLS)
    env.sandbox.events["web-001"].evidence_ids.append("E2")
    runtime.run_function(env, "read_event", {"event_id": "web-001"})
    runtime.run_function(env, "submit_report", {"event_id": "web-001", "verdict": "attack", "evidence_ids": ["E2"]})
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1]
    prepare(runtime, env)
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1] is None
    assert runtime.run_function(env, "block_ip", {"ip": "192.0.2.10"})[1]
    assert env.sandbox.blocked_ips == ["192.0.2.10"]
