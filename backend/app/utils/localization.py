# backend/app/utils/localization.py
"""
Comprehensive localization utility for multilingual chatbot support.
Provides language detection, message translation, and fallback mechanisms.
"""

import re
import logging
import json
import os
from typing import Dict, Any, Optional, Union, List
from dataclasses import dataclass
from enum import Enum

try:
    from langdetect import detect, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

logger = logging.getLogger("uvicorn")


class MessageType(Enum):
    """Types of messages that can be localized."""
    SECURITY_BLOCK = "security_block"
    SIGN_IN_REQUIRED = "sign_in_required"
    ERROR = "error"
    GENERAL = "general"


@dataclass
class LanguageInfo:
    """Information about a supported language."""
    code: str  # ISO 639-1 code (e.g., 'en', 'es')
    name: str  # English name (e.g., 'English', 'Spanish')
    native_name: str  # Native name (e.g., 'English', 'Español')
    rtl: bool = False  # Right-to-left writing direction


class LocalizationManager:
    """Centralized localization management for the chatbot."""
    
    # Supported languages with comprehensive metadata
    SUPPORTED_LANGUAGES = {
        'en': LanguageInfo('en', 'English', 'English'),
        'es': LanguageInfo('es', 'Spanish', 'Español'),
        'fr': LanguageInfo('fr', 'French', 'Français'),
        'de': LanguageInfo('de', 'German', 'Deutsch'),
        'it': LanguageInfo('it', 'Italian', 'Italiano'),
        'pt': LanguageInfo('pt', 'Portuguese', 'Português'),
        'nl': LanguageInfo('nl', 'Dutch', 'Nederlands'),
        'ru': LanguageInfo('ru', 'Russian', 'Русский'),
        'zh': LanguageInfo('zh', 'Chinese', '中文'),
        'ja': LanguageInfo('ja', 'Japanese', '日本語'),
        'ko': LanguageInfo('ko', 'Korean', '한국어'),
        'ar': LanguageInfo('ar', 'Arabic', 'العربية', rtl=True),
        'he': LanguageInfo('he', 'Hebrew', 'עברית', rtl=True),
        'hi': LanguageInfo('hi', 'Hindi', 'हिन्दी'),
        'th': LanguageInfo('th', 'Thai', 'ไทย'),
        'vi': LanguageInfo('vi', 'Vietnamese', 'Tiếng Việt'),
        'tr': LanguageInfo('tr', 'Turkish', 'Türkçe'),
        'pl': LanguageInfo('pl', 'Polish', 'Polski'),
        'cs': LanguageInfo('cs', 'Czech', 'Čeština'),
        'hu': LanguageInfo('hu', 'Hungarian', 'Magyar'),
    }

    # Default fallback messages in multiple languages
    FALLBACK_MESSAGES = {
        # Appended after links that need a BYU-Pathway / BYU-Idaho sign-in
        # (app/engine/login_links.py). One entry per SUPPORTED_LANGUAGES code
        # (tests/test_login_links.py checks this). en is source; the rest are
        # LLM translations pending a native-speaker pass. Tagalog isn't a
        # supported language here, so a tl entry could never be shown.
        MessageType.SIGN_IN_REQUIRED: {
            'en': "(sign-in required)",
            'es': "(requiere iniciar sesión)",
            'fr': "(connexion requise)",
            'de': "(Anmeldung erforderlich)",
            'it': "(accesso richiesto)",
            'pt': "(requer login)",
            'nl': "(inloggen vereist)",
            'ru': "(требуется вход)",
            'zh': "（需要登录）",
            'ja': "（サインインが必要）",
            'ko': "(로그인 필요)",
            'ar': "(يتطلب تسجيل الدخول)",
            'he': "(נדרשת התחברות)",
            'hi': "(साइन इन आवश्यक)",
            'th': "(ต้องลงชื่อเข้าใช้)",
            'vi': "(cần đăng nhập)",
            'tr': "(oturum açmak gerekir)",
            'pl': "(wymagane logowanie)",
            'cs': "(vyžaduje přihlášení)",
            'hu': "(bejelentkezés szükséges)",
        },

        MessageType.SECURITY_BLOCK: {
            'en': [
                "Sorry, I can't answer that; could you please rephrase your question and make it shorter?",
                "I'm sorry, but I can't assist with that request. If there's something else you'd like to talk about or ask, I'm here to help!",
                "Sorry, I can't comply with that request. If you want, I can help with something else or answer a different question."
            ],
            'es': [
                "Lo siento, no puedo responder eso; ¿podrías reformular tu pregunta y hacerla más corta?",
                "Lo siento, no puedo ayudar con esa solicitud. ¡Si hay algo más de lo que te gustaría hablar o preguntar, estoy aquí para ayudar!",
                "Lo siento, no puedo cumplir con esa solicitud. Si quieres, puedo ayudar con algo más o responder una pregunta diferente."
            ],
            'fr': [
                "Désolé, je ne peux pas répondre à cela ; pourriez-vous reformuler votre question et la raccourcir ?",
                "Je suis désolé, mais je ne peux pas vous aider avec cette demande. S'il y a autre chose dont vous aimeriez parler ou demander, je suis là pour vous aider !",
                "Désolé, je ne peux pas répondre à cette demande. Si vous voulez, je peux vous aider avec autre chose ou répondre à une question différente."
            ],
            'de': [
                "Entschuldigung, ich kann das nicht beantworten; könnten Sie Ihre Frage umformulieren und kürzer machen?",
                "Es tut mir leid, aber ich kann bei dieser Anfrage nicht helfen. Wenn es etwas anderes gibt, worüber Sie sprechen oder fragen möchten, bin ich hier, um zu helfen!",
                "Entschuldigung, ich kann dieser Anfrage nicht nachkommen. Wenn Sie möchten, kann ich bei etwas anderem helfen oder eine andere Frage beantworten."
            ],
            'it': [
                "Scusa, non posso rispondere a questo; potresti riformulare la tua domanda e renderla più breve?",
                "Mi dispiace, ma non posso aiutare con quella richiesta. Se c'è qualcos'altro di cui ti piacerebbe parlare o chiedere, sono qui per aiutare!",
                "Scusa, non posso soddisfare quella richiesta. Se vuoi, posso aiutare con qualcos'altro o rispondere a una domanda diversa."
            ],
            'pt': [
                "Desculpe, não posso responder isso; você poderia reformular sua pergunta e torná-la mais curta?",
                "Sinto muito, mas não posso ajudar com essa solicitação. Se há algo mais sobre o que você gostaria de falar ou perguntar, estou aqui para ajudar!",
                "Desculpe, não posso atender a essa solicitação. Se você quiser, posso ajudar com outra coisa ou responder a uma pergunta diferente."
            ],
            'ru': [
                "Извините, я не могу на это ответить; не могли бы вы переформулировать свой вопрос и сделать его короче?",
                "Извините, но я не могу помочь с этим запросом. Если есть что-то еще, о чем вы хотели бы поговорить или спросить, я здесь, чтобы помочь!",
                "Извините, я не могу выполнить этот запрос. Если хотите, я могу помочь с чем-то другим или ответить на другой вопрос."
            ],
            'zh': [
                "抱歉，我无法回答这个问题；您能重新表述您的问题并使其更简短吗？",
                "很抱歉，我无法协助处理该请求。如果您还有其他想讨论或询问的事情，我在这里为您提供帮助！",
                "抱歉，我无法满足该请求。如果您愿意，我可以帮助处理其他事情或回答不同的问题。"
            ],
            'ja': [
                "申し訳ございませんが、それにはお答えできません。質問を言い換えて短くしていただけますか？",
                "申し訳ございませんが、そのリクエストにはお手伝いできません。他に話したいことや質問したいことがありましたら、お手伝いします！",
                "申し訳ございませんが、そのリクエストにはお応えできません。よろしければ、他のことをお手伝いしたり、別の質問にお答えしたりできます。"
            ],
            'ko': [
                "죄송합니다. 그것에 대해서는 답변할 수 없습니다. 질문을 다시 표현하고 더 짧게 만들어 주실 수 있나요?",
                "죄송하지만 그 요청에 대해서는 도움을 드릴 수 없습니다. 다른 이야기하고 싶거나 물어보고 싶은 것이 있으시면 기꺼이 도와드리겠습니다!",
                "죄송합니다. 그 요청에는 응할 수 없습니다. 원하신다면 다른 것을 도와드리거나 다른 질문에 답변해 드릴 수 있습니다."
            ]
        },
        
    }
    
    # ------------------------------------------------------------------
    # Short-text language-detection bias (lesson #19 / localization audit
    # Gap #2). The underlying `langdetect` library is unreliable on short
    # input: a 2-5 word English message with a typo or a single accented
    # token gets confidently mislabelled as Dutch/French/German/Italian.
    # Production Langfuse data shows ~100% of nl-detected traces and nearly
    # all fr/de/it-detected traces are English speakers.
    #
    # The fix: a non-English detection on SHORT text is only trusted when
    # there is corroborating evidence — either explicit foreign-language
    # word indicators or sufficient length. Below that bar we fall back to
    # English. Spanish and Portuguese are the project's real non-English
    # traffic, so their indicator lists are deliberately rich enough that
    # even a one-word message ("Hola", "Obrigado") clears the bar.
    # ------------------------------------------------------------------

    # A non-English `langdetect` result is only trusted on short text once
    # the input reaches this many characters (audit recommendation: 40).
    SHORT_TEXT_CONFIDENCE_CHARS = 40

    # Minimum corroborating foreign-language indicators required to accept
    # a non-English detection on text shorter than SHORT_TEXT_CONFIDENCE_CHARS.
    MIN_FOREIGN_INDICATORS = 3

    # Accented characters that strongly suggest a Romance language (es / pt /
    # fr / it). Each occurrence counts as one foreign indicator. NOTE: a
    # single stray accent (e.g. an English "café" or "résumé") will not on
    # its own clear MIN_FOREIGN_INDICATORS — that is intentional.
    _ROMANCE_ACCENT_CHARS = set("áéíóúüñ¿¡çãõàâêîôûàèìòùäöü")

    # Per-language characteristic words. These are intentionally biased
    # toward es / pt (the real non-English traffic) so that genuine short
    # Spanish / Portuguese messages clear the indicator bar. fr / it lists
    # are kept smaller — short fr/it detections are almost entirely noise.
    _FOREIGN_WORD_INDICATORS: Dict[str, set] = {
        'es': {
            'hola', 'gracias', 'buenos', 'buenas', 'dias', 'días', 'tardes',
            'noches', 'cuando', 'cuándo', 'que', 'qué', 'como', 'cómo',
            'donde', 'dónde', 'por', 'para', 'con', 'una', 'uno', 'unos',
            'unas', 'del', 'los', 'las', 'está', 'están', 'estoy', 'muy',
            'más', 'año', 'años', 'semestre', 'bloque', 'registro',
            'matrícula', 'matricula', 'graduación', 'graduacion', 'clase',
            'clases', 'curso', 'cursos', 'quiero', 'necesito', 'puedo',
            'tengo', 'abre', 'cierra', 'fecha', 'fechas', 'ayuda',
            'pregunta', 'también', 'pero', 'este', 'esta', 'información',
            'informacion', 'pago', 'pagar', 'escribe', 'historia', 'sobre',
            'muéstrame', 'muestrame', 'mostrar', 'calendario',
        },
        'pt': {
            'olá', 'ola', 'obrigado', 'obrigada', 'bom', 'boa', 'dia',
            'tarde', 'noite', 'você', 'voce', 'quando', 'como', 'onde',
            'que', 'para', 'com', 'uma', 'uns', 'umas', 'dos', 'das',
            'está', 'estão', 'estou', 'muito', 'mais', 'ano', 'anos',
            'semestre', 'bloco', 'registro', 'matrícula', 'matricula',
            'graduação', 'graduacao', 'aula', 'aulas', 'curso', 'cursos',
            'quero', 'preciso', 'posso', 'tenho', 'abre', 'fecha', 'data',
            'datas', 'ajuda', 'pergunta', 'também', 'mas', 'este', 'esta',
            'informação', 'informacao', 'começa', 'comeca', 'custa',
            'quanto', 'pago', 'pagar', 'exibir', 'calendário', 'calendario',
        },
        'fr': {
            'bonjour', 'merci', 'quand', 'comment', 'où', 'une', 'des',
            'pour', 'avec', 'vous', 'calendrier', 'bloc', 'semestre',
            'inscription', 'cours', 'écris', 'histoire', 'montrer',
        },
        'it': {
            'ciao', 'grazie', 'quando', 'come', 'dove', 'una', 'gli',
            'per', 'con', 'calendario', 'blocco', 'semestre', 'iscrizione',
            'corso', 'mostrami',
        },
    }

    # English domain / function-word patterns. Used to recognise that an
    # ambiguous short message is really English even when langdetect's
    # low-confidence guess says otherwise. Includes common typos.
    _ENGLISH_INDICATOR_PATTERNS = [
        r'\b(when|wen|whe|what|wut|wat|where|whr|why|how|hw|who|whcih|which)\b',
        r'\b(is|are|am|was|were|be|can|cud|could|would|wud|will|shall|should|do|does|did|done)\b',
        r'\b(the|a|an|and|or|but|in|on|at|to|for|of|with|by|from|about)\b',
        r'\b(i|you|u|he|she|it|we|they|me|him|her|us|them|my|your|ur)\b',
        r'\b(this|that|these|those|here|there|now|then|please|pls|plz|thanks|thx|thank|hi|hello|helo|hey)\b',
        r'\b(block|term|semester|registration|registraton|deadline|payment|'
        r'grade|grades|grad|calendar|tuition|class|classes|course|courses|'
        r'start|starts|open|opens|due|pay)\b',
    ]

    @classmethod
    def _count_foreign_indicators(cls, text: str) -> Dict[str, Any]:
        """
        Score a piece of text for corroborating non-English evidence.

        Returns a dict with:
          - per-language word-match counts under 'es' / 'pt' / 'fr' / 'it'
          - 'accents': count of Romance accented characters
          - 'best_lang': the language with the highest word-match count
            (None if there are zero word matches)
          - 'best_word_count': that language's word-match count
          - 'total': total corroborating indicators (best-language word
            matches + accent characters). Used against MIN_FOREIGN_INDICATORS.
        """
        lowered = text.lower()
        # Tokens may carry Romance accented characters; keep those in \w-ish
        # word extraction so "cuándo" matches the 'cuándo' indicator.
        tokens = set(re.findall(r"[a-záéíóúüñçãõàâêîôûèìòùäö]+", lowered))

        per_lang = {
            lang: len(tokens & words)
            for lang, words in cls._FOREIGN_WORD_INDICATORS.items()
        }
        accents = sum(1 for ch in lowered if ch in cls._ROMANCE_ACCENT_CHARS)

        best_lang = None
        best_word_count = 0
        for lang, count in per_lang.items():
            if count > best_word_count:
                best_lang = lang
                best_word_count = count

        result: Dict[str, Any] = dict(per_lang)
        result['accents'] = accents
        result['best_lang'] = best_lang
        result['best_word_count'] = best_word_count
        # Corroborating evidence = the strongest single language's word
        # matches plus any accent characters. We do NOT sum across
        # languages because es/pt share many cognates and double-counting
        # would inflate the score for genuinely English text.
        result['total'] = best_word_count + accents
        return result

    @classmethod
    def _count_english_indicators(cls, text: str) -> int:
        """Count how many English function/domain-word patterns match."""
        return sum(
            1 for pattern in cls._ENGLISH_INDICATOR_PATTERNS
            if re.search(pattern, text, re.IGNORECASE)
        )

    @classmethod
    def detect_language(cls, text: str, fallback: str = 'en') -> str:
        """
        Detect the language of input text using langdetect.

        Short text is handled with an English-bias guard: a non-English
        `langdetect` result is only accepted when the input is at least
        SHORT_TEXT_CONFIDENCE_CHARS long OR carries at least
        MIN_FOREIGN_INDICATORS corroborating foreign-language indicators.
        Otherwise the result falls back to English. This prevents short
        English messages (typos, a stray accented token) from being
        mislabelled as Dutch/French/German/Italian, while still detecting
        genuine short Spanish / Portuguese messages.

        Args:
            text: The text to analyze
            fallback: Language code to return if detection fails

        Returns:
            ISO 639-1 language code
        """
        if not LANGDETECT_AVAILABLE:
            logger.warning("langdetect not available, using fallback language")
            return fallback

        if not text or not text.strip():
            logger.info("Empty text provided, using fallback language")
            return fallback

        try:
            # Clean the text for better language detection
            clean_text = re.sub(r'[<>\[\]{}|]', ' ', text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()

            char_count = len(clean_text)
            word_count = len(clean_text.split())
            is_short = char_count < cls.SHORT_TEXT_CONFIDENCE_CHARS

            # Score corroborating non-English evidence up front — it is
            # needed both to rescue genuine short es/pt and to validate
            # any short non-English detection.
            foreign = cls._count_foreign_indicators(clean_text)
            english_indicators = cls._count_english_indicators(clean_text)

            detected_lang = detect(clean_text)
            normalized_lang = cls.normalize_language_code(detected_lang)

            # Unsupported language -> fallback regardless of length.
            if normalized_lang not in cls.SUPPORTED_LANGUAGES:
                logger.warning(
                    f"Detected unsupported language: {detected_lang}, "
                    f"using fallback: {fallback}"
                )
                return fallback

            # English detection is always trusted — the bias guard only
            # ever pushes ambiguous results TOWARD English, never away.
            if normalized_lang == 'en':
                # Length, not text: questions may name students (CLAUDE.md §9.2).
                logger.info(f"Detected language: en ({len(clean_text)} chars)")
                return 'en'

            # --- Non-English detection on LONG text: trust it. ---
            if not is_short:
                logger.info(f"Detected language: {normalized_lang} ({len(clean_text)} chars)")
                return normalized_lang

            # --- Non-English detection on SHORT text: needs evidence. ---
            #
            # Step 1: if the corroborating indicators clearly point at a
            # specific Romance language (es/pt/fr/it), trust that — even
            # over langdetect's noisy raw guess. This rescues genuine
            # short Spanish / Portuguese ("Hola", "Bom dia", "Obrigado")
            # that langdetect otherwise scatters across tr/so/etc.
            best_lang = foreign['best_lang']
            best_word_count = foreign['best_word_count']
            if (
                best_lang in cls.SUPPORTED_LANGUAGES
                and best_word_count >= 1
                and best_word_count >= english_indicators
            ):
                logger.info(
                    f"Short non-English text corroborated by "
                    f"{best_word_count} {best_lang} word indicator(s); "
                    f"using {best_lang}"
                )
                return best_lang

            # Step 2: accept langdetect's own short non-English guess only
            # when there are enough generic foreign indicators. Otherwise
            # the guess is almost certainly noise -> fall back to English.
            if foreign['total'] >= cls.MIN_FOREIGN_INDICATORS:
                logger.info(
                    f"Short non-English text ({normalized_lang}) cleared "
                    f"the foreign-indicator bar ({foreign['total']} "
                    f"indicators); using {normalized_lang}"
                )
                return normalized_lang

            logger.info(
                f"Short text detected as '{normalized_lang}' but lacks "
                f"corroborating evidence ({foreign['total']} foreign "
                f"indicators, {english_indicators} English indicators, "
                f"{char_count} chars); biasing to English"
            )
            return 'en'

        except LangDetectException as e:
            logger.warning(f"Language detection failed: {e}, using fallback: {fallback}")
            return fallback
        except Exception as e:
            logger.error(f"Unexpected error in language detection: {e}, using fallback: {fallback}")
            return fallback

    @classmethod
    def detect_language_confident(cls, text: str, fallback: str = 'en') -> tuple[str, bool]:
        """Like `detect_language`, but ALSO reports whether the result is a
        CONFIDENT determination from the text (True) versus an ambiguous /
        short-text fallback (False).

        Used by per-request language resolution: a CONFIDENT prompt detection
        should win over the manual gear-menu pref (the pref is only a BACKUP for
        when the prompt's language can't be determined). See `_resolve_user_language`.

        Confidence rules (derived from the same signals `detect_language` uses):
          - A supported NON-English result is only ever returned by
            `detect_language` when the text was long OR carried corroborating
            foreign-language evidence -> CONFIDENT.
          - An English result is confident only when the text actually looks
            English: it is not short (>= SHORT_TEXT_CONFIDENCE_CHARS) OR carries
            at least one English indicator. A SHORT result with no English
            evidence is the bias-to-English fallback (lesson #19) — i.e.
            "couldn't tell" -> NOT confident (defer to the gear pref).
        """
        lang = cls.detect_language(text, fallback=fallback)
        if not text or not text.strip():
            return (lang, False)
        clean = re.sub(r'[<>\[\]{}|]', ' ', text)
        clean = re.sub(r'\s+', ' ', clean).strip()
        if lang != 'en':
            # detect_language only yields a supported non-en code when it had
            # positive evidence (long text or corroborating indicators).
            return (lang, True)
        is_short = len(clean) < cls.SHORT_TEXT_CONFIDENCE_CHARS
        if not is_short or cls._count_english_indicators(clean) >= 1:
            return ('en', True)
        # Short 'en' with no English evidence == the bias fallback == "couldn't tell".
        return ('en', False)

    @classmethod
    def normalize_language_code(cls, lang_code: str) -> str:
        """
        Normalize language code to handle variants.
        
        Args:
            lang_code: Raw language code (e.g., 'zh-cn', 'en-US')
            
        Returns:
            Normalized language code (e.g., 'zh', 'en')
        """
        if not lang_code:
            return 'en'
        
        # Convert to lowercase and extract base language
        base_lang = lang_code.lower().split('-')[0].split('_')[0]
        
        # Handle special cases
        if base_lang in ['zh', 'chinese']:
            return 'zh'
        elif base_lang in ['ar', 'arabic']:
            return 'ar'
        elif base_lang in ['he', 'hebrew']:
            return 'he'
        # Catalan/Galician → Spanish (langdetect often confuses short Spanish)
        elif base_lang in ['ca', 'gl']:
            return 'es'

        return base_lang
    
    @classmethod
    def get_language_info(cls, lang_code: str) -> LanguageInfo:
        """
        Get comprehensive language information.
        
        Args:
            lang_code: Language code to look up
            
        Returns:
            LanguageInfo object
        """
        normalized_code = cls.normalize_language_code(lang_code)
        return cls.SUPPORTED_LANGUAGES.get(normalized_code, cls.SUPPORTED_LANGUAGES['en'])
    
    @classmethod
    def is_language_supported(cls, lang_code: str) -> bool:
        """
        Check if a language is supported.
        
        Args:
            lang_code: Language code to check
            
        Returns:
            True if supported, False otherwise
        """
        normalized_code = cls.normalize_language_code(lang_code)
        return normalized_code in cls.SUPPORTED_LANGUAGES
    
    @classmethod
    def get_message(cls, message_type: MessageType, lang_code: str, 
                   variation: Optional[int] = None, **kwargs) -> Union[str, Dict[str, str]]:
        """
        Get a localized message.
        
        Args:
            message_type: Type of message to retrieve
            lang_code: Target language code
            variation: For message types with multiple variations (like security blocks)
            **kwargs: Additional parameters for message formatting
            
        Returns:
            Localized message string or dictionary
        """
        normalized_lang = cls.normalize_language_code(lang_code)
        
        # Fall back to English if language not supported
        if normalized_lang not in cls.SUPPORTED_LANGUAGES:
            logger.warning(f"Language {lang_code} not supported, falling back to English")
            normalized_lang = 'en'
        
        # Get the message from fallback messages
        messages = cls.FALLBACK_MESSAGES.get(message_type, {})
        lang_messages = messages.get(normalized_lang, messages.get('en', {}))
        
        if isinstance(lang_messages, list):
            # Handle multiple variations (like security block messages)
            if variation is not None and 0 <= variation < len(lang_messages):
                return lang_messages[variation]
            else:
                # Return random variation if no specific variation requested
                import random
                return random.choice(lang_messages)
        elif isinstance(lang_messages, dict):
            # Handle dictionary messages (like site index)
            return lang_messages
        elif isinstance(lang_messages, str):
            # Handle simple string messages
            return lang_messages.format(**kwargs) if kwargs else lang_messages
        else:
            # Fallback to English if anything goes wrong
            english_messages = messages.get('en', {})
            if isinstance(english_messages, list):
                import random
                return random.choice(english_messages)
            return english_messages
    
    @classmethod
    def get_security_message(cls, lang_code: str, variation: Optional[int] = None) -> str:
        """
        Get a localized security block message.
        
        Args:
            lang_code: Target language code
            variation: Specific variation index (0-2), None for random
            
        Returns:
            Localized security message
        """
        return cls.get_message(MessageType.SECURITY_BLOCK, lang_code, variation)
    
    @classmethod
    def get_supported_languages(cls) -> List[Dict[str, str]]:
        """
        Get list of all supported languages with metadata.
        
        Returns:
            List of language dictionaries
        """
        return [
            {
                'code': info.code,
                'name': info.name,
                'native_name': info.native_name,
                'rtl': info.rtl
            }
            for info in cls.SUPPORTED_LANGUAGES.values()
        ]
    
    @classmethod 
    def load_external_translations(cls, file_path: str) -> bool:
        """
        Load translations from an external JSON file.
        This allows for easy translation updates without code changes.
        
        Args:
            file_path: Path to JSON translation file
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"Translation file not found: {file_path}")
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                external_translations = json.load(f)
            
            # Merge external translations with built-in ones
            for message_type_str, translations in external_translations.items():
                try:
                    message_type = MessageType(message_type_str)
                    if message_type not in cls.FALLBACK_MESSAGES:
                        cls.FALLBACK_MESSAGES[message_type] = {}
                    
                    cls.FALLBACK_MESSAGES[message_type].update(translations)
                    logger.info(f"Loaded external translations for {message_type_str}")
                    
                except ValueError:
                    logger.warning(f"Unknown message type in translation file: {message_type_str}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to load external translations: {e}")
            return False