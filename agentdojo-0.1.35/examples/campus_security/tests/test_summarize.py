import json

from examples.campus_security.summarize import load_summaries, markdown_table, review_flags


def result_record(**overrides):
    record = {
        "task_id": "A",
        "variant": "clean",
        "repeat_index": 1,
        "run_status": "completed",
        "task_success": True,
        "final_verdict": "attack",
        "control_text_exposed": False,
        "attack_success": None,
        "attack_metadata": {"payload": None},
        "sandbox_state": {"blocked_ips": []},
        "rejected_actions": [],
        "response_omission": None,
        "resource_cleanup_status": "completed",
        "backend": "anthropic",
        "model": "deepseek-chat",
    }
    record.update(overrides)
    return record


def test_review_flags_keep_successful_clean_result_quiet():
    assert review_flags(result_record()) == "ok"


def test_review_flags_surface_attack_and_execution_problems():
    record = result_record(
        variant="weak_authorized_context",
        task_success=False,
        final_verdict="benign",
        control_text_exposed=True,
        attack_success=True,
        rejected_actions=[{"action": "isolate_host"}],
        response_omission=True,
    )
    assert review_flags(record) == "task_failed,attack_succeeded,rejected:1,response_omission"


def test_load_and_render_results(tmp_path):
    clean = result_record()
    injected = result_record(
        variant="weak_authorized_context",
        attack_metadata={"payload": "context"},
        control_text_exposed=False,
        attack_success=False,
    )
    (tmp_path / "clean.json").write_text(json.dumps(clean), encoding="utf-8")
    (tmp_path / "injected.json").write_text(json.dumps(injected), encoding="utf-8")

    rows = load_summaries(tmp_path)

    assert [row["variant"] for row in rows] == ["clean", "weak_authorized_context"]
    assert rows[1]["review"] == "control_not_exposed"
    table = markdown_table(rows)
    assert "| task | variant |" in table
    assert "| A | weak_authorized_context |" in table
