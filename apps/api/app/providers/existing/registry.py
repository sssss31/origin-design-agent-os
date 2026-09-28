from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.providers.existing.base import ExistingAgentProvider
from app.providers.existing.chatgpt_workspace import ChatGPTWorkspaceAgent
from app.providers.existing.http_json import HttpJsonAgent
from app.providers.existing.openai_responses import OpenAIResponsesAgent

CONNECTION_TYPES: dict[str, str] = {
    "origin": "Origin-built agent (prompt composed here)",
    "openai_responses": "OpenAI Responses API (existing GPT agent)",
    "http": "HTTP JSON endpoint (existing agent API)",
    "chatgpt_workspace": "ChatGPT Workspace Agent (API trigger; reply stays in ChatGPT)",
}


def build_existing_providers(
    settings: Settings, *, transport: Any = None
) -> dict[str, ExistingAgentProvider]:
    return {
        "openai_responses": OpenAIResponsesAgent(transport=transport),
        "http": HttpJsonAgent(settings, transport=transport),
        "chatgpt_workspace": ChatGPTWorkspaceAgent(transport=transport),
    }
