"""Portul catre model. Motorul vede doar ModelPort; testele folosesc un model fals, fara retea."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "medium"
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def model_id_from_env() -> str:
    return os.environ.get("EC_QUOTE_MODEL") or DEFAULT_MODEL


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class ModelReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    # Continutul brut al raspunsului, retrimis neschimbat in bucla de unelte.
    raw_content: Any = None


class ModelError(RuntimeError):
    """Modelul nu a putut raspunde (retea, limita, eroare API)."""


class ModelPort(Protocol):
    def complete(self, *, system: list[dict], tools: list[dict], messages: list[dict]) -> ModelReply: ...


class AnthropicModel:
    """Invelis subtire peste anthropic.Anthropic().messages.create (clientul este injectat)."""

    def __init__(self, client: Any = None, model: str | None = None, effort: str | None = None,
                 max_tokens: int = 16000, fallbacks: bool = True) -> None:
        if client is None:
            import anthropic  # import tarziu: testele nu au nevoie de SDK

            client = anthropic.Anthropic()
        self._client = client
        self.model = model or model_id_from_env()
        self.effort = effort or os.environ.get("EC_QUOTE_EFFORT") or DEFAULT_EFFORT
        self.max_tokens = max_tokens
        self.fallbacks = fallbacks

    def complete(self, *, system: list[dict], tools: list[dict], messages: list[dict]) -> ModelReply:
        # Gandirea adaptiva este implicita; adancimea se regleaza doar prin effort.
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "tools": tools,
            "messages": messages,
            "output_config": {"effort": self.effort},
        }
        try:
            if self.fallbacks:
                # Un refuz al clasificatorului este reluat pe modelul recomandat, in acelasi apel.
                response = self._client.beta.messages.create(
                    betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                response = self._client.messages.create(**kwargs)
        except Exception as exc:  # erorile SDK sunt deja reincercate de client
            raise ModelError(f"{type(exc).__name__}: {exc}") from exc

        stop_reason = response.stop_reason or "end_turn"
        if stop_reason == "refusal":
            return ModelReply(stop_reason="refusal", raw_content=response.content)
        texts: list[str] = []
        calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                texts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, input=dict(block.input or {})))
        return ModelReply(text="\n".join(t for t in texts if t).strip(), tool_calls=calls,
                          stop_reason=stop_reason, raw_content=response.content)
