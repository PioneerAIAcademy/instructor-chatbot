// frontend/app/components/ui/chat/utils/localization.ts
/**
 * Frontend localization utilities for the chatbot.
 * Provides lightweight translation support for UI elements.
 */

export interface DraftComposerTranslations {
  emailLabel: string;
  messageLabel: string;
  subjectLabel: string;
  addSubjectPlaceholder: string;
}

/**
 * Normalize language code to handle variants.
 * @param langCode - Raw language code (e.g., 'zh-cn', 'en-US')
 * @returns Normalized language code (e.g., 'zh', 'en')
 */
function normalizeLanguageCode(langCode?: string): string {
  if (!langCode) {
    return "en";
  }

  // Convert to lowercase and extract base language
  const baseLang = langCode.toLowerCase().split("-")[0].split("_")[0];

  // Handle special cases
  if (baseLang === "zh" || baseLang === "chinese") {
    return "zh";
  }

  return baseLang;
}

const DRAFT_COMPOSER_TRANSLATIONS: Record<string, DraftComposerTranslations> = {
  en: {
    emailLabel: "Email",
    messageLabel: "Message",
    subjectLabel: "Subject",
    addSubjectPlaceholder: "Add subject",
  },
  es: {
    emailLabel: "Correo",
    messageLabel: "Mensaje",
    subjectLabel: "Asunto",
    addSubjectPlaceholder: "Agregar asunto",
  },
  pt: {
    emailLabel: "E-mail",
    messageLabel: "Mensagem",
    subjectLabel: "Assunto",
    addSubjectPlaceholder: "Adicionar assunto",
  },
  fr: {
    emailLabel: "E-mail",
    messageLabel: "Message",
    subjectLabel: "Objet",
    addSubjectPlaceholder: "Ajouter un objet",
  },
  it: {
    emailLabel: "Email",
    messageLabel: "Messaggio",
    subjectLabel: "Oggetto",
    addSubjectPlaceholder: "Aggiungi oggetto",
  },
  de: {
    emailLabel: "E-Mail",
    messageLabel: "Nachricht",
    subjectLabel: "Betreff",
    addSubjectPlaceholder: "Betreff hinzufügen",
  },
  ru: {
    emailLabel: "Письмо",
    messageLabel: "Сообщение",
    subjectLabel: "Тема",
    addSubjectPlaceholder: "Добавить тему",
  },
  ja: {
    emailLabel: "メール",
    messageLabel: "メッセージ",
    subjectLabel: "件名",
    addSubjectPlaceholder: "件名を追加",
  },
  zh: {
    emailLabel: "邮件",
    messageLabel: "消息",
    subjectLabel: "主题",
    addSubjectPlaceholder: "添加主题",
  },
  ko: {
    emailLabel: "이메일",
    messageLabel: "메시지",
    subjectLabel: "제목",
    addSubjectPlaceholder: "제목 추가",
  },
};

export function getDraftComposerTranslations(
  languageCode?: string,
): DraftComposerTranslations {
  const normalizedCode = normalizeLanguageCode(languageCode);
  return (
    DRAFT_COMPOSER_TRANSLATIONS[normalizedCode] || DRAFT_COMPOSER_TRANSLATIONS.en
  );
}
