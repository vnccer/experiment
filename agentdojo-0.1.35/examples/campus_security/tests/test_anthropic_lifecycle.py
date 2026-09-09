import asyncio
from types import SimpleNamespace

from agentdojo.types import ChatAssistantMessage, ChatUserMessage, text_content_block_from_string
from examples.campus_security import anthropic_lifecycle
from examples.campus_security.anthropic_lifecycle import StableLoopAnthropicLLM


def test_anthropic_client_queries_and_closes_on_one_loop(monkeypatch):
    loop_ids = []

    class FakeAsyncClient:
        async def close(self):
            loop_ids.append(id(asyncio.get_running_loop()))

    async def fake_request(*args, **kwargs):
        loop_ids.append(id(asyncio.get_running_loop()))
        return object()

    monkeypatch.setattr(anthropic_lifecycle, "chat_completion_request", fake_request)
    monkeypatch.setattr(
        anthropic_lifecycle,
        "_anthropic_to_assistant_message",
        lambda completion: ChatAssistantMessage(role="assistant", content=[], tool_calls=None),
    )
    llm = StableLoopAnthropicLLM(FakeAsyncClient(), "example-model")
    runtime = SimpleNamespace(functions={})
    messages = [ChatUserMessage(role="user", content=[text_content_block_from_string("task")])]
    llm.query("task", runtime, None, messages, {})
    llm.query("task", runtime, None, messages, {})
    llm.close()
    llm.close()

    assert len(loop_ids) == 3
    assert len(set(loop_ids)) == 1
