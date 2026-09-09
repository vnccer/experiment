"""Print a compact review table for one campus-security result directory."""

import argparse
import json
from pathlib import Path


def display(value):
    if value is None:
        return "-"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def review_flags(record):
    flags = []
    if record.get("run_status") != "completed":
        flags.append(f"status:{record.get('run_status', 'missing')}")
    if not record.get("task_success", False):
        flags.append("task_failed")
    if record.get("attack_success") is True:
        flags.append("attack_succeeded")
    metadata = record.get("attack_metadata") or {}
    if metadata.get("payload") and not record.get("control_text_exposed", False):
        flags.append("control_not_exposed")
    rejected = record.get("rejected_actions") or []
    if rejected:
        flags.append(f"rejected:{len(rejected)}")
    if record.get("response_omission") is True:
        flags.append("response_omission")
    if record.get("resource_cleanup_status") == "error":
        flags.append("cleanup_error")
    return ",".join(flags) if flags else "ok"


def summarize_record(path):
    record = json.loads(path.read_text(encoding="utf-8"))
    sandbox = record.get("sandbox_state") or {}
    blocked_ips = sandbox.get("blocked_ips") or []
    return {
        "task": record.get("task_id"),
        "variant": record.get("variant"),
        "repeat": record.get("repeat_index"),
        "status": record.get("run_status"),
        "task_ok": record.get("task_success"),
        "verdict": record.get("final_verdict"),
        "exposed": record.get("control_text_exposed"),
        "attack_ok": record.get("attack_success"),
        "blocked_ips": ",".join(blocked_ips) if blocked_ips else "-",
        "rejected": len(record.get("rejected_actions") or []),
        "review": review_flags(record),
        "file": path.name,
        "backend": record.get("backend"),
        "model": record.get("model"),
    }


def load_summaries(directory):
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise ValueError(f"No JSON results found in {directory}")
    rows = [summarize_record(path) for path in paths]
    return sorted(rows, key=lambda row: (display(row["task"]), display(row["variant"]), display(row["repeat"])))


def markdown_table(rows):
    columns = (
        "task",
        "variant",
        "repeat",
        "status",
        "task_ok",
        "verdict",
        "exposed",
        "attack_ok",
        "blocked_ips",
        "rejected",
        "review",
    )
    output = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        output.append("| " + " | ".join(display(row[column]) for column in columns) + " |")
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("result_dir", type=Path, help="Directory containing per-episode JSON result files.")
    args = parser.parse_args()
    try:
        rows = load_summaries(args.result_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    identities = sorted({f"{display(row['backend'])}/{display(row['model'])}" for row in rows})
    print(f"episodes={len(rows)} backend/model={','.join(identities)}")
    print(markdown_table(rows))
    flagged = [row for row in rows if row["review"] != "ok"]
    if flagged:
        print("\nReview files:")
        for row in flagged:
            print(f"- {row['file']}: {row['review']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
