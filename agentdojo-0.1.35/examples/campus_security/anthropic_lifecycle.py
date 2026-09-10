"""Anthropic adapter lifecycle fix scoped to the campus experiment."""

import asyncio
import re

from agentdojo.agent_pipeline.llms.anthropic_llm import (
    AnthropicLLM,
    _anthropic_to_assistant_message,
    _conversation_to_anthropic,
    _function_to_anthropic,
    chat_completion_request,
)


class StableLoopAnthropicLLM(AnthropicLLM):
    """Keep one async client on one event loop, then close both explicitly.

    AgentDojo 0.1.35 calls ``asyncio.run`` for every model turn. Reusing the
    resulting AsyncAnthropic/httpx client across those short-lived loops can
    leave pooled connections attached to an already closed loop. This local
    adapter preserves the original request and response handling while making
    the loop lifetime match one experiment episode.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._event_loop = asyncio.new_event_loop()
        self._closed = False

    def query(self, query, runtime, env, messages=(), extra_args=None):
        if self._closed:
            raise RuntimeError("Anthropic adapter is already closed")
        extra_args = extra_args if extra_args is not None else {}
        system_prompt, anthropic_messages = _conversation_to_anthropic(messages)
        if "claude-3-sonnet" in self.model or "claude-3-haiku" in self.model:
            system_prompt = f"{self._COT_PROMPT}\n\n{system_prompt}"
        anthropic_tools = [_function_to_anthropic(tool) for tool in runtime.functions.values()]
        completion = self._event_loop.run_until_complete(
            chat_completion_request(
                self.client,
                self.model,
                anthropic_messages,
                anthropic_tools,
                max_tokens=self._MAX_TOKENS,
                system_prompt=system_prompt,
                temperature=self.temperature,
                thinking_budget_tokens=self.thinking_budget_tokens,
            )
        )
        response_id = getattr(completion, "id", None)
        response_model = getattr(completion, "model", None)
        if response_id is not None:
            extra_args.setdefault("provider_response_ids", []).append(str(response_id))
        if response_model is not None:
            extra_args.setdefault("provider_response_models", []).append(str(response_model))
        output = _anthropic_to_assistant_message(completion)
        if output["tool_calls"] is not None:
            output["tool_calls"] = [
                call for call in output["tool_calls"] if re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", call.function)
            ]
        return query, runtime, env, [*messages, output], extra_args

    def close(self):
        if self._closed:
            return
        try:
            self._event_loop.run_until_complete(self.client.close())
        finally:
            self._event_loop.close()
            self._closed = True
