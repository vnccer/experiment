"""Summarize the frozen identifier experiment with reviewed, traceable annotations."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(directory):
    plan = read(directory / "plan.json")
    rows = [read(p) for p in sorted((directory / "raw").glob("*.json"))]
    expected = {s["slot"]: s for s in plan["schedule"]}
    if len(rows) != 20 or len({r["slot"] for r in rows}) != 20:
        raise ValueError("All 20 unique scheduled results are required")
    for row in rows:
        assert {k: row[k] for k in ("slot", "condition", "repeat")} == expected[row["slot"]]
    # The existing pipeline's default extra_args dictionary accumulated provider metadata.
    # Audit actual messages separately and derive per-episode metadata without altering raw.
    previous_ids, previous_models = [], []
    metadata = []
    for row in rows:
        messages = row["messages"]
        preview = read(directory / "input_previews" / f"{row['condition']}.json")
        assert [m["role"] for m in messages[:2]] == ["system", "user"]
        assert messages[0]["content"][0]["content"] == preview["system_prompt"]
        assert messages[1]["content"][0]["content"] == preview["task_prompt"]
        assert sum(m["role"] == "system" for m in messages) == 1
        assert sum(m["role"] == "user" for m in messages) == 1
        reads = [m for m in messages if m["role"] == "tool" and m["tool_call"]["function"] == "read_event"]
        assert len(reads) == 1 and not reads[0]["error"]
        assert json.loads(reads[0]["content"][0]["content"]) == preview["read_event_response"]
        ids, models = row["provider_response_ids"], row["provider_response_models"]
        assert ids[:len(previous_ids)] == previous_ids and models[:len(previous_models)] == previous_models
        new_ids, new_models = ids[len(previous_ids):], models[len(previous_models):]
        assert len(new_ids) == len(new_models) == row["llm_call_count"]
        metadata.append({"slot": row["slot"], "provider_response_ids": new_ids,
                         "provider_response_models": new_models})
        previous_ids, previous_models = ids, models
    audit = {
        "actual_messages_match_frozen_condition": True,
        "one_fresh_system_and_user_message_per_episode": True,
        "read_event_responses_match_frozen_previews": True,
        "raw_provider_metadata_is_cumulative": True,
        "explanation": "Default extra_args in the existing AgentPipeline accumulated provider IDs/models only; actual conversations and sandbox state were fresh. Per-episode metadata below is the verified prefix difference; raw files are unchanged.",
        "per_episode_metadata": metadata,
    }
    with (directory / "measurement_audit.json").open("x", encoding="utf-8") as stream:
        json.dump(audit, stream, ensure_ascii=False, indent=2)
    annotations = read(directory / "reason_annotations.json")
    reviewed = {a["slot"]: a for a in annotations["annotations"]}
    assert len(reviewed) == len(annotations["annotations"]) == 20
    for row in rows:
        annotation = reviewed[row["slot"]]
        path = directory / annotation["raw_file"]
        assert read(path)["slot"] == row["slot"] and sha(path) == annotation["raw_sha256"]
        assert annotation["label"] in {"adopted", "not_adopted", "indeterminate", "unobservable"}
        assert annotation["evidence_excerpt"] in row["final_text"]
    groups = {}
    for condition in sorted({r["condition"] for r in rows}):
        selected = [r for r in rows if r["condition"] == condition]
        groups[condition] = {
            "n": len(selected), "completed": sum(r["run_status"] == "completed" for r in selected),
            "verdict_counts": dict(Counter(r["final_verdict"] or "missing" for r in selected)),
            "report_missing": sum(r["report_missing"] for r in selected),
            "task_success": sum(r["task_success"] for r in selected),
            "exposed": sum(r["control_text_exposed"] for r in selected),
            "classification_escape": sum(r["classification_escape"] for r in selected),
            "reason_labels": dict(Counter(reviewed[r["slot"]]["label"] for r in selected)),
            "mean_anchor_recall_all_episodes": mean(r["anchor_recall"] for r in selected),
            "llm_calls": sum(r["llm_call_count"] for r in selected),
            "mean_seconds": mean(r["elapsed_time"] for r in selected),
            "slots": [r["slot"] for r in selected],
        }
    result = {
        "plan_sha256": sha(directory / "plan.json"),
        "criteria_sha256": sha(directory / "criteria.json"),
        "annotations_sha256": sha(directory / "reason_annotations.json"),
        "measurement_audit_sha256": sha(directory / "measurement_audit.json"),
        "total_episodes": len(rows), "groups": groups,
        "model_requested": plan["model"],
        "models_returned": sorted({m for r in rows for m in r["provider_response_models"]}),
        "total_llm_calls": sum(r["llm_call_count"] for r in rows),
        "total_seconds": sum(r["elapsed_time"] for r in rows),
        "token_usage_available_episodes": sum(r["token_usage"] is not None for r in rows),
        "rejected_action_count": sum(len(r["rejected_actions"]) for r in rows),
        "executed_response_action_count": sum(a["action"] in {"block_ip", "isolate_host"}
                                               for r in rows for a in r["executed_actions"]),
        "cleanup_counts": dict(Counter(r["resource_cleanup_status"] for r in rows)),
        "missing_report_slots": [r["slot"] for r in rows if r["report_missing"]],
        "limitations": [
            "One development event with five repeats per cell; not independent event families.",
            "New experiment using extant fixed payload; not a reproduction of the unavailable historical rationale payload.",
            "Reason labels are agent-reviewed final observable text, not an independent human assessment or hidden reasoning.",
            "Token usage and provider stop reasons are not exposed by the existing adapter.",
            "The fixed user-agent pair changes browser text as well as adding the payload; no length-matched neutral-text control.",
            "Identifier replacement changes semantics and tokenization together; no isolated semantic-effect estimate.",
            "Raw provider ID/model arrays accumulated across episodes; measurement_audit.json provides validated per-episode differences. Model input histories were verified fresh.",
        ],
    }
    with (directory / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    summarize(parser.parse_args().directory)
