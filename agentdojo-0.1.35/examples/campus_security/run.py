"""Run from the repository root: python -m examples.campus_security.run."""

import argparse
import json
import os
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel

from .pipeline import IterationLimitError, ScriptedLLM, build_pipeline
from .runtime import CampusRuntime
from .tasks import EVENT_ID, SOURCE_IP, task_suite
from .variants import VARIANT_CHOICES, assess_injection, prepare_variant, resolve_variants


def json_default(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Unsupported record type: {type(value).__name__}")


def run_task(
    task_id,
    llm,
    output_dir,
    backend="scripted",
    model_name="scripted-demo",
    max_iters=8,
    variant="clean",
    repeat_index=1,
):
    task = task_suite.get_user_task_by_id({"A": "user_task_0", "B": "user_task_1"}[task_id])
    env = task_suite.load_and_inject_default_environment({})
    env, attack_metadata = prepare_variant(env, EVENT_ID, variant)
    pipeline, tracked = build_pipeline(llm, max_iters)
    started_at = datetime.now(timezone.utc).isoformat()
    start = perf_counter()
    success = False
    status = "completed"
    error_type = None
    cleanup_status = "not_required"
    cleanup_error_type = None
    try:
        success, _ = task_suite.run_task_with_pipeline(
            pipeline, task, None, {}, runtime_class=CampusRuntime, environment=env
        )
        if not tracked.messages or tracked.messages[-1]["role"] != "assistant":
            status = "incomplete"
        elif tracked.messages[-1].get("tool_calls"):
            status = "iteration_limit"
    except IterationLimitError:
        status = "iteration_limit"
    except Exception as exc:
        # Never persist exception text: SDK errors can contain credentials or request data.
        status, error_type = "error", type(exc).__name__
    finally:
        elapsed = perf_counter() - start
        close = getattr(llm, "close", None)
        if callable(close):
            try:
                close()
                cleanup_status = "completed"
            except Exception as exc:
                cleanup_status, cleanup_error_type = "error", type(exc).__name__
    state = env.sandbox
    report = state.reports.get(EVENT_ID)
    proposals = []
    for message in tracked.messages:
        if message["role"] == "assistant":
            for call in message.get("tool_calls") or []:
                proposals.append(
                    {
                        "sequence": len(proposals) + 1,
                        "action": call.function,
                        "args": dict(call.args),
                        "call_id": call.id,
                    }
                )
    final_text = ""
    if tracked.messages and tracked.messages[-1]["role"] == "assistant":
        final_text = "\n".join(
            block["content"] for block in tracked.messages[-1].get("content") or [] if block["type"] == "text"
        )
    result = {
        "schema_version": 2,
        "task_id": task_id,
        "agentdojo_task_id": task.ID,
        "event_id": EVENT_ID,
        "variant": variant,
        "repeat_index": repeat_index,
        "attack_metadata": attack_metadata,
        **assess_injection(attack_metadata, tracked.messages, report, status),
        "response_omission": (SOURCE_IP not in state.blocked_ips) if task_id == "B" and status == "completed" else None,
        "backend": backend,
        "model": model_name,
        "is_real_llm": backend != "scripted",
        "started_at": started_at,
        "run_status": status,
        "error_type": error_type,
        "resource_cleanup_status": cleanup_status,
        "resource_cleanup_error_type": cleanup_error_type,
        "final_verdict": report.verdict if report else None,
        "verdict_source": "accepted_submit_report",
        "final_text": final_text,
        "evidence_ids": report.evidence_ids if report else [],
        "proposed_actions": proposals,
        "rejected_actions": state.rejected_actions,
        "executed_actions": state.executed_actions,
        "task_success": bool(success and status == "completed"),
        "unauthorized_action_attempt": bool(state.rejected_actions),
        "tool_call_count": len(proposals),
        "llm_call_count": tracked.calls,
        "elapsed_time": elapsed,
        "token_usage": tracked.extra_args.get("token_usage"),
        "token_usage_status": "available" if tracked.extra_args.get("token_usage") else "not_exposed_by_adapter",
        "sandbox_state": state.model_dump(include={"read_event_ids", "reports", "blocked_ips", "isolated_hosts"}),
        "messages": tracked.messages,
        "versions": {
            "python": platform.python_version(),
            "agentdojo": version("agentdojo"),
            "anthropic": version("anthropic"),
            "openai": version("openai"),
        },
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{backend}-task-{task_id}-{variant}-repeat-{repeat_index}-{uuid4().hex}.json"
    path = output_dir / filename
    serialized = json.dumps(result, ensure_ascii=False, indent=2, default=json_default)
    path.write_text(serialized, encoding="utf-8")
    return json.loads(serialized), path


def make_llm(backend, model):
    if backend == "scripted":
        return ScriptedLLM()
    if not model:
        raise ValueError("A real backend requires --model with the provider's model identifier.")
    if backend == "anthropic":
        if not os.getenv("ANTHROPIC_AUTH_TOKEN"):
            raise ValueError("Configure ANTHROPIC_AUTH_TOKEN locally before running; do not paste it into chat.")
        from anthropic import AsyncAnthropic

        from .anthropic_lifecycle import StableLoopAnthropicLLM

        client = AsyncAnthropic(api_key=None, auth_token=os.environ["ANTHROPIC_AUTH_TOKEN"], timeout=60, max_retries=0)
        return StableLoopAnthropicLLM(client, model, max_tokens=1024)
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("Configure OPENAI_API_KEY locally before running; do not paste it into chat.")
    from openai import OpenAI

    from agentdojo.agent_pipeline.llms.openai_llm import OpenAILLM

    return OpenAILLM(OpenAI(timeout=60, max_retries=0), model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("scripted", "anthropic", "openai"), default="scripted")
    parser.add_argument("--model", help="Actual provider model identifier; no AgentDojo enum alias required.")
    parser.add_argument("--task", choices=("A", "B", "both"), default="both")
    parser.add_argument("--variant", choices=VARIANT_CHOICES, default="clean", help="Fixed development event variant.")
    parser.add_argument("--output-dir", type=Path, default=Path("runs/campus_security"))
    parser.add_argument("--max-iters", type=int, default=8, help="Maximum execution batches after first LLM response.")
    parser.add_argument("--repeats", type=int, default=1, help="Independent episodes to run for each task/variant.")
    parser.add_argument(
        "--env-file", type=Path, help="Explicit local dotenv file; existing environment takes precedence."
    )
    args = parser.parse_args()
    if args.max_iters < 1:
        parser.error("--max-iters must be positive")
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.env_file:
        if not args.env_file.is_file():
            parser.error("--env-file does not exist")
        from dotenv import load_dotenv

        load_dotenv(args.env_file, override=False)
    tasks = ("A", "B") if args.task == "both" else (args.task,)
    variants = resolve_variants(args.variant)
    all_success = True
    for task_id in tasks:
        for variant in variants:
            for repeat_index in range(1, args.repeats + 1):
                try:
                    llm = make_llm(args.backend, args.model)
                except ValueError as exc:
                    parser.error(str(exc))
                result, path = run_task(
                    task_id,
                    llm,
                    args.output_dir,
                    args.backend,
                    args.model or "scripted-demo",
                    args.max_iters,
                    variant,
                    repeat_index,
                )
                all_success = all_success and result["task_success"]
                all_success = all_success and result["resource_cleanup_status"] != "error"
                print(
                    f"Task {task_id} variant={variant} repeat={repeat_index}: status={result['run_status']} "
                    f"success={result['task_success']} cleanup={result['resource_cleanup_status']} "
                    f"real_llm={result['is_real_llm']} calls={result['tool_call_count']} "
                    f"exposed={result['control_text_exposed']} attack_success={result['attack_success']} "
                    f"result={path}"
                )
    return 0 if all_success else 1


if __name__ == "__main__":
    raise SystemExit(main())
