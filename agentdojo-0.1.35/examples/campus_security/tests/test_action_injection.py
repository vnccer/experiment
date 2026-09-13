import json

from examples.campus_security import variants
from examples.campus_security.action_injection import (
    ACTION_FIXTURES,
    CONDITIONS,
    FIXTURE_DIR,
    REPEATS,
    SEED,
    build_schedule,
    preview_inputs,
    summarize,
)
from examples.campus_security.tasks import EVENT_ID, task_suite


def test_fixtures_are_registered_single_field_payloads():
    for name, filename in ACTION_FIXTURES.items():
        fixture = json.loads((FIXTURE_DIR / filename).read_text(encoding="utf-8"))
        assert name in variants.VARIANTS
        assert fixture["field"] == "raw_log.user_agent"
        for forbidden in ('"', "\r", "\n"):
            assert forbidden not in fixture["payload"]


def test_schedule_is_balanced_block_randomization():
    planned = build_schedule(SEED)
    assert len(planned) == len(CONDITIONS) * REPEATS
    assert [slot["slot"] for slot in planned] == list(range(1, len(planned) + 1))
    for block in range(1, REPEATS + 1):
        conditions = [slot["condition"] for slot in planned if slot["block"] == block]
        assert sorted(conditions) == sorted(CONDITIONS)


def test_only_user_agent_changes_and_exposure_expectation_holds():
    preview = preview_inputs()["conditions"]
    env = task_suite.load_and_inject_default_environment({})
    baselines = {
        condition: variants.prepare_variant(env, EVENT_ID, condition)[0].sandbox.events[EVENT_ID]
        for condition in CONDITIONS
    }
    for condition, event in baselines.items():
        assert preview[condition]["raw_log"] == event.raw_log
        assert preview[condition]["control_text_exposed_expected"] == (condition != "clean")
        for other in CONDITIONS:
            assert event.model_dump(exclude={"raw_log"}) == baselines[other].model_dump(exclude={"raw_log"})


def test_summarize_counts_only_valid_episodes():
    rows = [
        {
            "slot": 1,
            "block": 1,
            "condition": "action_retarget_block",
            "run_status": "completed",
            "unauthorized_action_attempt": True,
            "rejected_actions": [{"action": "block_ip"}],
            "response_omission": False,
            "final_verdict": "attack",
            "task_success": False,
            "control_text_exposed": True,
        },
        {
            "slot": 2,
            "block": 1,
            "condition": "action_retarget_block",
            "run_status": "error",
            "unauthorized_action_attempt": False,
            "rejected_actions": [],
            "response_omission": None,
            "final_verdict": None,
            "task_success": False,
            "control_text_exposed": False,
        },
    ]
    summary = summarize("unused", {"config": {"model": "test"}}, rows)
    cell = summary["per_condition"]["action_retarget_block"]
    assert cell["episodes"] == 2
    assert cell["valid_episodes"] == 1
    assert cell["invalid_episodes"] == 1
    assert cell["unauthorized_action_attempt"] == 1
    assert cell["response_omission"] == 0
    assert summary["per_condition"]["clean"]["episodes"] == 0
