import logging
import os
import re

from fastapi import APIRouter

from app.api.routers.models import ChatConfig


config_router = r = APIRouter()

logger = logging.getLogger("uvicorn")


def parse_starters(raw: str | None) -> list[str] | None:
    """Starter questions from CONVERSATION_STARTERS: one per line. A literal
    backslash-n also separates them, because many hosting dashboards can't
    store a real newline in an environment variable."""
    if not raw or not raw.strip():
        return None
    questions = [q.strip() for q in re.split(r"\r?\n|\\n", raw) if q.strip()]
    return questions or None


@r.get("")
async def chat_config() -> ChatConfig:
    return ChatConfig(starter_questions=parse_starters(os.getenv("CONVERSATION_STARTERS")))

