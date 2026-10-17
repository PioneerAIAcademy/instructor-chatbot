"""Localized status messages for pipeline progress indicators.

These drive the user-visible "thinking" indicator. They cover the
llama-index pipeline events (retrieval / query / synthesis / reranking /
LLM).

They follow the LANGUAGE THE USER PROMPTED IN — every getter takes a
`lang` argument. English keeps a pool of variants for variety; other
languages get one natural string per stage (per CLAUDE.md lesson #91 —
for a transient, see-once indicator the variety is not the value, the
right localized phrase is). Unsupported languages fall back to English.

en/es/pt are reviewed-quality; fr/it/ja/ko/zh/tl are LLM translations
pending a native-speaker pass (upstream tracks this in pathway-chatbot
docs/i18n/native-speaker-review-queue.md).
"""

import random

_SUPPORTED = ("en", "es", "pt", "fr", "it", "ja", "ko", "zh", "tl")


def _norm(lang: str | None) -> str:
    """Normalize a language code to a supported key, else 'en'."""
    if not lang or not isinstance(lang, str):
        return "en"
    base = lang.strip().lower().replace("_", "-").split("-")[0]
    return base if base in _SUPPORTED else "en"


# Stage 2: Retrieval start messages
RETRIEVAL_MESSAGES = {
    "en": [
        "Looking for content...",
        "Searching knowledge base...",
        "Finding relevant sources...",
        "Retrieving information...",
    ],
    "es": ["Buscando en la base de conocimientos..."],
    "pt": ["Pesquisando na base de conhecimento..."],
    "fr": ["Recherche dans la base de connaissances..."],
    "it": ["Ricerca nella base di conoscenza..."],
    "ja": ["ナレッジベースを検索しています..."],
    "ko": ["지식 베이스를 검색하고 있습니다..."],
    "zh": ["正在搜索知识库..."],
    "tl": ["Naghahanap sa knowledge base..."],
}

# Stage 1: Query understanding messages
QUERY_MESSAGES = {
    "en": [
        "Understanding the question...",
        "Interpreting request...",
        "Analyzing query...",
    ],
    "es": ["Entendiendo la pregunta..."],
    "pt": ["Entendendo a pergunta..."],
    "fr": ["Compréhension de la question..."],
    "it": ["Comprensione della domanda..."],
    "ja": ["質問を理解しています..."],
    "ko": ["질문을 이해하고 있습니다..."],
    "zh": ["正在理解问题..."],
    "tl": ["Inuunawa ang tanong..."],
}

# Stage 3: Synthesis/generation messages
SYNTHESIZE_MESSAGES = {
    "en": [
        "Synthesizing response...",
        "Drafting answer...",
        "Composing response...",
    ],
    "es": ["Redactando la respuesta..."],
    "pt": ["Redigindo a resposta..."],
    "fr": ["Rédaction de la réponse..."],
    "it": ["Stesura della risposta..."],
    "ja": ["回答を作成しています..."],
    "ko": ["답변을 작성하고 있습니다..."],
    "zh": ["正在起草答案..."],
    "tl": ["Binubuo ang sagot..."],
}

# Stage 3.5: LLM generation start messages
LLM_MESSAGES = {
    "en": [
        "Generating response...",
        "Producing answer...",
        "Formulating reply...",
    ],
    "es": ["Generando la respuesta..."],
    "pt": ["Gerando a resposta..."],
    "fr": ["Génération de la réponse..."],
    "it": ["Generazione della risposta..."],
    "ja": ["回答を生成しています..."],
    "ko": ["답변을 생성하고 있습니다..."],
    "zh": ["正在生成回复..."],
    "tl": ["Bumubuo ng tugon..."],
}

# Stage 4: Reranking messages
RERANKING_MESSAGES = {
    "en": [
        "Ranking sources by relevance...",
        "Analyzing source quality...",
        "Selecting best matches...",
        "Prioritizing results...",
        "Evaluating sources...",
    ],
    "es": ["Evaluando las fuentes..."],
    "pt": ["Avaliando as fontes..."],
    "fr": ["Évaluation des sources..."],
    "it": ["Valutazione delle fonti..."],
    "ja": ["情報源を評価しています..."],
    "ko": ["출처를 평가하고 있습니다..."],
    "zh": ["正在评估来源..."],
    "tl": ["Sinusuri ang mga pinagmulan..."],
}


def _pick(pool: dict[str, list[str]], lang: str | None) -> str:
    """Pick a random variant from `pool` for `lang`, English fallback."""
    variants = pool.get(_norm(lang)) or pool["en"]
    return random.choice(variants)


def get_retrieval_start_message(lang: str | None = "en") -> str:
    """Returns a random retrieval start message in `lang`."""
    return _pick(RETRIEVAL_MESSAGES, lang)


def get_query_message(lang: str | None = "en") -> str:
    """Returns a random query understanding message in `lang`."""
    return _pick(QUERY_MESSAGES, lang)


def get_synthesize_message(lang: str | None = "en") -> str:
    """Returns a random synthesis message in `lang`."""
    return _pick(SYNTHESIZE_MESSAGES, lang)


def get_llm_message(lang: str | None = "en") -> str:
    """Returns a random LLM generation message in `lang`."""
    return _pick(LLM_MESSAGES, lang)


def get_reranking_message(lang: str | None = "en") -> str:
    """Returns a random reranking message in `lang`."""
    return _pick(RERANKING_MESSAGES, lang)
