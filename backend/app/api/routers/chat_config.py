import logging
import os
import re

from fastapi import APIRouter, Query

from app.api.routers.models import ChatConfig


config_router = r = APIRouter()

logger = logging.getLogger("uvicorn")


# The welcome screen's cards when CONVERSATION_STARTERS is unset. Each is
# "Title | question": the frontend shows the title and asks the question.
DEFAULT_STARTERS = [
    "Pay dates | When do I get paid this block?",
    "Extend a due date | How do I give one student more time on an assignment in Canvas?",
    "An unresolved student issue | A student has submitted several tickets with no resolution. What can I do?",
    "Write a welcome message | Write a welcome message for my students.",
]

# The same cards in the other interface languages (frontend/app/lib/i18n.ts).
DEFAULT_STARTERS_BY_LANGUAGE = {
    "en": DEFAULT_STARTERS,
    "es": [
        "Fechas de pago | ¿Cuándo me pagan en este bloque?",
        "Extender una fecha de entrega | ¿Cómo le doy a un estudiante más tiempo para una tarea en Canvas?",
        "Un problema sin resolver | Un estudiante ha enviado varios tickets y no ha tenido solución. ¿Qué puedo hacer?",
        "Mensaje de bienvenida | Escribe un mensaje de bienvenida para mis estudiantes.",
    ],
    "pt": [
        "Datas de pagamento | Quando vou receber neste bloco?",
        "Prorrogar um prazo | Como dou mais tempo a um aluno em uma tarefa no Canvas?",
        "Um problema sem solução | Um aluno abriu vários chamados e ainda não teve solução. O que posso fazer?",
        "Mensagem de boas-vindas | Escreva uma mensagem de boas-vindas para os meus alunos.",
    ],
}


def _language(lang: str | None) -> str:
    """"es-MX" -> "es"; anything unsupported -> "en"."""
    code = (lang or "").strip().lower().replace("_", "-").split("-")[0]
    return code if code in DEFAULT_STARTERS_BY_LANGUAGE else "en"


def parse_starters(raw: str | None, lang: str = "en") -> list[str] | None:
    """Starter questions from CONVERSATION_STARTERS: one per line. A literal
    backslash-n also separates them, because many hosting dashboards can't
    store a real newline in an environment variable.

    Unset: the built-in cards for `lang`. Set but blank: no starters."""
    if raw is None:
        return list(DEFAULT_STARTERS_BY_LANGUAGE[_language(lang)])
    if not raw.strip():
        return None
    questions = [q.strip() for q in re.split(r"\r?\n|\\n", raw) if q.strip()]
    return questions or None


def starters_for(lang: str | None) -> list[str] | None:
    """English reads CONVERSATION_STARTERS; Spanish and Portuguese read
    CONVERSATION_STARTERS_ES / _PT. Each falls back to its built-in cards
    when its own variable is unset."""
    code = _language(lang)
    name = "CONVERSATION_STARTERS" if code == "en" else f"CONVERSATION_STARTERS_{code.upper()}"
    return parse_starters(os.getenv(name), code)


@r.get("")
async def chat_config(lang: str | None = Query(default=None, max_length=16)) -> ChatConfig:
    """`?lang=es|pt` returns the welcome cards in that interface language."""
    return ChatConfig(starter_questions=starters_for(lang))

