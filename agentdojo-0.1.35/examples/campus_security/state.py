from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentdojo.functions_runtime import TaskEnvironment


class Event(BaseModel):
    event_id: str
    timestamp: str
    src_ip: str
    dst_asset: str
    raw_log: str
    evidence_ids: list[str]


class Policy(BaseModel):
    """Trusted configuration; never inferred from event text or model output."""

    model_config = ConfigDict(frozen=True)
    task_id: str
    event_id: str
    allowed_actions: tuple[str, ...]
    allowed_ip: str | None = None
    allowed_asset: str
    required_evidence_ids: tuple[str, ...]


class Report(BaseModel):
    event_id: str
    verdict: Literal["attack", "benign", "uncertain"]
    evidence_ids: list[str]


class Sandbox(BaseModel):
    events: dict[str, Event]
    asset_inventory: dict[str, str]
    policy: Policy | None = None
    read_event_ids: list[str] = Field(default_factory=list)
    reports: dict[str, Report] = Field(default_factory=dict)
    blocked_ips: list[str] = Field(default_factory=list)
    isolated_hosts: list[str] = Field(default_factory=list)
    proposed_actions: list[dict] = Field(default_factory=list)
    rejected_actions: list[dict] = Field(default_factory=list)
    executed_actions: list[dict] = Field(default_factory=list)


class CampusEnvironment(TaskEnvironment):
    sandbox: Sandbox
