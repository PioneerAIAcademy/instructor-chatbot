// frontend/app/lib/chrome-strings.ts
//
// Every string in the app's interface, in the three interface languages
// (owner, 2026-10-20: English, Spanish, Portuguese; this replaces CLAUDE.md
// §13 Q12's "English UI"). The language comes from Settings → Language, or
// the browser's language when none is picked (app/lib/i18n.ts). Answers
// follow the question's language, and the picked language when the question
// doesn't make one clear (backend chat._resolve_language).
//
// Spanish uses "tú" and Portuguese (Brazil) uses "você", as upstream's
// reviewed translations do; shared wording is upstream's, with the product
// name changed to the Instructor Assistant.

import type { LangCode } from "./i18n";

export interface ChromeStrings {
  // Header
  headerTitle: string; // "Instructor Assistant"
  homeAria: string; // the logo link
  newChat: string; // "New chat"
  // Chat input: on the welcome screen, and once a chat has started
  inputPlaceholder: string;
  replyPlaceholder: string;
  // Notes under the chat input: student privacy (CLAUDE.md §9.2) and where
  // answers come from
  ferpaLabel: string; // "Privacy:"
  ferpaNotice: string; // "Don't include student names, IDs, or grades."
  aiNoteShort: string; // phones
  aiNoteLong: string; // sm+
  // Chat screen
  chatErrorFriendly: string; // the error banner
  dismissErrorAria: string;
  scrollToLatestAria: string;
  startersAria: string; // the welcome cards
  followUpsAria: string; // an answer's suggested follow-ups
  // Settings menu
  settingsTitle: string; // "Settings"
  settingsTheme: string; // "Theme"
  settingsLanguage: string; // "Language"
  settingsHelp: string; // "Help"
  settingsFeedback: string; // "Send feedback"
  settingsLanguageAuto: string; // "Auto"
  // Themes
  themeLight: string;
  themeDark: string;
  themeSystem: string;
  // Welcome screen: "<time of day> <question>", then a subtitle
  greetingMorning: string; // "Good morning."
  greetingAfternoon: string; // "Good afternoon."
  greetingEvening: string; // "Good evening."
  greetingAfterHours: string; // "Working late?"
  greetingQuestion: string; // "What can I help with?"
  welcomeSub: string;
  // Buttons / tooltips
  sendButton: string; // "Send"
  regenerateButton: string; // "Regenerate"
  stopButton: string; // "Stop"
  copyButton: string; // "Copy"
  // Editing a sent question
  editButton: string; // "Edit"
  editCancel: string; // "Cancel"
  editSave: string; // "Save"
  // Thinking indicator — shown before the first backend status event lands
  thinkingDefault: string; // "Thinking…"
  // Sources: drawer, chips, citation badges
  sourcesTitle: string; // "Sources"
  sourcesCountSingular: string; // "{n} cited passage" — use {n} placeholder
  sourcesCountPlural: string; // "{n} cited passages"
  sourcesCloseAria: string; // "Close sources"
  sourcesOpenAria: string; // "Open {n} answer sources"
  sourceTypeGuide: string; // "Instructor guide (PDF)" (CLAUDE.md §8.3)
  sourceTypeExternal: string; // "External page · {host}"
  sourceFallbackTitle: string; // "Source", when a source has no title
  sourceNumberAria: string; // "Source {n}: {title}"
  opensInNewTab: string; // "(opens in a new tab)"
  showMoreCitationOne: string; // "Show 1 more citation"
  showMoreCitations: string; // "Show {n} more citations"
  // Per-message thumb feedback (UserFeedbackComponent)
  feedbackLoveTitle: string; // "Love this"
  feedbackNeedsImprovementTitle: string; // "Needs improvement"
  feedbackPlaceholder: string; // textarea placeholder
  feedbackCancelButton: string; // "Cancel"
  feedbackSubmitButton: string; // "Submit"
  feedbackThanksToast: string; // "Thanks for your feedback!"
  // General feedback drawer (gear menu → Send feedback)
  gfDrawerTitle: string; // "Send feedback"
  gfDrawerDescription: string;
  gfDrawerLabel: string; // "Describe your feedback (required)"
  gfDrawerPlaceholder: string;
  gfDrawerSensitiveInfo: string;
  gfDrawerCancel: string; // "Cancel"
  gfDrawerSend: string; // "Send"
  gfDrawerSending: string; // "Sending..."
  gfDrawerCloseTitle: string; // "Close"
  gfDrawerEmptyToast: string;
  gfDrawerSuccessToast: string;
  gfDrawerErrorToast: string;
  // Draft composer (email/message editor). Its header ("Email", "Subject")
  // follows the draft's language instead (ui/chat/utils/localization.ts).
  draftSend: string;
  draftCopy: string; // "Copy"
  draftCopied: string; // "Copied!"
  draftOutlookWork: string; // "Outlook (Work or School)"
  draftOutlookPersonal: string; // "Outlook.com (Personal)"
  draftAcceptOrUndo: string; // "Accept or Undo?"
  draftAccept: string;
  draftUndo: string;
  draftTextStyle: string; // "Text style: {style}"
  draftStyleText: string; // "Text"
  draftStyleH1: string;
  draftStyleH2: string;
  draftStyleH3: string;
  draftNumberedList: string;
  draftBulletedList: string;
  draftBold: string;
  draftItalic: string;
  draftUnderline: string;
  draftInsertLink: string;
  draftTweak: string; // "Tweak"
  draftTweakPlaceholder: string;
  draftApply: string;
  draftApplying: string;
  draftLinkPlaceholder: string;
  draftInsert: string;
  draftLinkSelectFirstToast: string; // "Select text to turn into a link."
  draftLinkInvalidUrlToast: string; // "Enter a valid link URL."
  draftTweakErrorToast: string; // "Please rephrase."
}

export const CHROME_STRINGS: Record<LangCode, ChromeStrings> = {
  en: {
    headerTitle: "Instructor Assistant",
    homeAria: "BYU-Pathway Instructor Assistant home",
    newChat: "New chat",
    inputPlaceholder: "Ask Instructor Assistant…",
    replyPlaceholder: "Reply to Instructor Assistant…",
    ferpaLabel: "Privacy:",
    ferpaNotice: "Don’t include student names, IDs, or grades.",
    aiNoteShort: "Answers come from instructor guides. Check important details.",
    aiNoteLong:
      "Answers come from BYU-Pathway instructor guides and the pages they link to. AI can make mistakes, so check important details.",
    chatErrorFriendly: "Something went wrong. Please try again.",
    dismissErrorAria: "Dismiss error",
    scrollToLatestAria: "Scroll to latest messages",
    startersAria: "Suggested questions",
    followUpsAria: "Suggested follow-up questions",
    settingsTitle: "Settings",
    settingsTheme: "Theme",
    settingsLanguage: "Language",
    settingsHelp: "Help",
    settingsFeedback: "Send feedback",
    settingsLanguageAuto: "Auto",
    themeLight: "Light",
    themeDark: "Dark",
    themeSystem: "System",
    greetingMorning: "Good morning.",
    greetingAfternoon: "Good afternoon.",
    greetingEvening: "Good evening.",
    greetingAfterHours: "Working late?",
    greetingQuestion: "What can I help with?",
    welcomeSub:
      "Ask about pay, contracts, Canvas, students, or anything in the instructor guides.",
    sendButton: "Send",
    regenerateButton: "Regenerate",
    stopButton: "Stop",
    copyButton: "Copy",
    editButton: "Edit",
    editCancel: "Cancel",
    editSave: "Save",
    thinkingDefault: "Thinking…",
    sourcesTitle: "Sources",
    sourcesCountSingular: "{n} cited passage",
    sourcesCountPlural: "{n} cited passages",
    sourcesCloseAria: "Close sources",
    sourcesOpenAria: "Open {n} answer sources",
    sourceTypeGuide: "Instructor guide (PDF)",
    sourceTypeExternal: "External page · {host}",
    sourceFallbackTitle: "Source",
    sourceNumberAria: "Source {n}: {title}",
    opensInNewTab: "(opens in a new tab)",
    showMoreCitationOne: "Show 1 more citation",
    showMoreCitations: "Show {n} more citations",
    feedbackLoveTitle: "Love this",
    feedbackNeedsImprovementTitle: "Needs improvement",
    feedbackPlaceholder:
      "What would have made this response more helpful for you?",
    feedbackCancelButton: "Cancel",
    feedbackSubmitButton: "Submit",
    feedbackThanksToast: "Thanks for your feedback!",
    gfDrawerTitle: "Send feedback",
    gfDrawerDescription:
      "Help us improve the BYU-Pathway Instructor Assistant. Share what happened and what you expected.",
    gfDrawerLabel: "Describe your feedback (required)",
    gfDrawerPlaceholder: "Tell us what prompted this feedback...",
    gfDrawerSensitiveInfo:
      "Please don’t include student names, IDs, grades, or other sensitive information.",
    gfDrawerCancel: "Cancel",
    gfDrawerSend: "Send",
    gfDrawerSending: "Sending...",
    gfDrawerCloseTitle: "Close",
    gfDrawerEmptyToast: "Please describe your feedback before sending.",
    gfDrawerSuccessToast: "Thanks for your feedback!",
    gfDrawerErrorToast: "Could not send feedback. Please try again.",
    draftSend: "Send",
    draftCopy: "Copy",
    draftCopied: "Copied!",
    draftOutlookWork: "Outlook (Work or School)",
    draftOutlookPersonal: "Outlook.com (Personal)",
    draftAcceptOrUndo: "Accept or Undo?",
    draftAccept: "Accept",
    draftUndo: "Undo",
    draftTextStyle: "Text style: {style}",
    draftStyleText: "Text",
    draftStyleH1: "Heading 1",
    draftStyleH2: "Heading 2",
    draftStyleH3: "Heading 3",
    draftNumberedList: "Numbered list",
    draftBulletedList: "Bulleted list",
    draftBold: "Bold",
    draftItalic: "Italic",
    draftUnderline: "Underline",
    draftInsertLink: "Insert link",
    draftTweak: "Tweak",
    draftTweakPlaceholder: "Describe the change to apply...",
    draftApply: "Apply",
    draftApplying: "Applying",
    draftLinkPlaceholder: "Paste a link...",
    draftInsert: "Insert",
    draftLinkSelectFirstToast: "Select text to turn into a link.",
    draftLinkInvalidUrlToast: "Enter a valid link URL.",
    draftTweakErrorToast: "Please rephrase.",
  },
  es: {
    headerTitle: "Asistente para Instructores",
    homeAria: "Inicio del Asistente para Instructores de BYU-Pathway",
    newChat: "Nuevo chat",
    inputPlaceholder: "Pregúntale al Asistente para Instructores…",
    replyPlaceholder: "Responde al Asistente para Instructores…",
    ferpaLabel: "Privacidad:",
    ferpaNotice: "No incluyas nombres, números de identificación ni calificaciones de estudiantes.",
    aiNoteShort: "Las respuestas vienen de las guías para instructores. Verifica los detalles importantes.",
    aiNoteLong:
      "Las respuestas vienen de las guías para instructores de BYU-Pathway y de las páginas que enlazan. La IA puede cometer errores, así que verifica los detalles importantes.",
    chatErrorFriendly: "Algo salió mal. Inténtalo de nuevo.",
    dismissErrorAria: "Cerrar el error",
    scrollToLatestAria: "Ir a los mensajes más recientes",
    startersAria: "Preguntas sugeridas",
    followUpsAria: "Preguntas de seguimiento sugeridas",
    settingsTitle: "Configuración",
    settingsTheme: "Tema",
    settingsLanguage: "Idioma",
    settingsHelp: "Ayuda",
    settingsFeedback: "Enviar comentarios",
    settingsLanguageAuto: "Automático",
    themeLight: "Claro",
    themeDark: "Oscuro",
    themeSystem: "Sistema",
    greetingMorning: "Buenos días.",
    greetingAfternoon: "Buenas tardes.",
    greetingEvening: "Buenas noches.",
    greetingAfterHours: "¿Trabajando hasta tarde?",
    greetingQuestion: "¿En qué puedo ayudarte?",
    welcomeSub:
      "Pregunta sobre pagos, contratos, Canvas, estudiantes o cualquier tema de las guías para instructores.",
    sendButton: "Enviar",
    regenerateButton: "Regenerar",
    stopButton: "Detener",
    copyButton: "Copiar",
    editButton: "Editar",
    editCancel: "Cancelar",
    editSave: "Guardar",
    thinkingDefault: "Pensando…",
    sourcesTitle: "Fuentes",
    sourcesCountSingular: "{n} pasaje citado",
    sourcesCountPlural: "{n} pasajes citados",
    sourcesCloseAria: "Cerrar fuentes",
    sourcesOpenAria: "Abrir {n} fuentes de la respuesta",
    sourceTypeGuide: "Guía para instructores (PDF)",
    sourceTypeExternal: "Página externa · {host}",
    sourceFallbackTitle: "Fuente",
    sourceNumberAria: "Fuente {n}: {title}",
    opensInNewTab: "(se abre en una pestaña nueva)",
    showMoreCitationOne: "Mostrar 1 cita más",
    showMoreCitations: "Mostrar {n} citas más",
    feedbackLoveTitle: "Me encanta",
    feedbackNeedsImprovementTitle: "Necesita mejorar",
    feedbackPlaceholder:
      "¿Qué habría hecho que esta respuesta te resultara más útil?",
    feedbackCancelButton: "Cancelar",
    feedbackSubmitButton: "Enviar",
    feedbackThanksToast: "¡Gracias por tus comentarios!",
    gfDrawerTitle: "Enviar comentarios",
    gfDrawerDescription:
      "Ayúdanos a mejorar el Asistente para Instructores de BYU-Pathway. Cuéntanos qué pasó y qué esperabas.",
    gfDrawerLabel: "Describe tus comentarios (obligatorio)",
    gfDrawerPlaceholder: "Cuéntanos qué motivó estos comentarios...",
    gfDrawerSensitiveInfo:
      "No incluyas nombres, números de identificación ni calificaciones de estudiantes, ni otra información confidencial.",
    gfDrawerCancel: "Cancelar",
    gfDrawerSend: "Enviar",
    gfDrawerSending: "Enviando...",
    gfDrawerCloseTitle: "Cerrar",
    gfDrawerEmptyToast: "Por favor, describe tus comentarios antes de enviarlos.",
    gfDrawerSuccessToast: "¡Gracias por tus comentarios!",
    gfDrawerErrorToast: "No se pudieron enviar los comentarios. Inténtalo de nuevo.",
    draftSend: "Enviar",
    draftCopy: "Copiar",
    draftCopied: "¡Copiado!",
    draftOutlookWork: "Outlook (trabajo o escuela)",
    draftOutlookPersonal: "Outlook.com (personal)",
    draftAcceptOrUndo: "¿Aceptar o deshacer?",
    draftAccept: "Aceptar",
    draftUndo: "Deshacer",
    draftTextStyle: "Estilo de texto: {style}",
    draftStyleText: "Texto",
    draftStyleH1: "Título 1",
    draftStyleH2: "Título 2",
    draftStyleH3: "Título 3",
    draftNumberedList: "Lista numerada",
    draftBulletedList: "Lista con viñetas",
    draftBold: "Negrita",
    draftItalic: "Cursiva",
    draftUnderline: "Subrayado",
    draftInsertLink: "Insertar enlace",
    draftTweak: "Ajustar",
    draftTweakPlaceholder: "Describe el cambio que quieres hacer...",
    draftApply: "Aplicar",
    draftApplying: "Aplicando",
    draftLinkPlaceholder: "Pega un enlace...",
    draftInsert: "Insertar",
    draftLinkSelectFirstToast: "Selecciona el texto que quieras convertir en enlace.",
    draftLinkInvalidUrlToast: "Ingresa una URL válida.",
    draftTweakErrorToast: "Por favor, reformula la solicitud.",
  },
  pt: {
    headerTitle: "Assistente do Instrutor",
    homeAria: "Início do Assistente do Instrutor da BYU-Pathway",
    newChat: "Nova conversa",
    inputPlaceholder: "Pergunte ao Assistente do Instrutor…",
    replyPlaceholder: "Responda ao Assistente do Instrutor…",
    ferpaLabel: "Privacidade:",
    ferpaNotice: "Não inclua nomes, números de identificação nem notas de alunos.",
    aiNoteShort: "As respostas vêm dos guias do instrutor. Confira os detalhes importantes.",
    aiNoteLong:
      "As respostas vêm dos guias do instrutor da BYU-Pathway e das páginas para as quais eles apontam. A IA pode cometer erros, então confira os detalhes importantes.",
    chatErrorFriendly: "Algo deu errado. Tente novamente.",
    dismissErrorAria: "Fechar o erro",
    scrollToLatestAria: "Ir para as mensagens mais recentes",
    startersAria: "Perguntas sugeridas",
    followUpsAria: "Perguntas de acompanhamento sugeridas",
    settingsTitle: "Configurações",
    settingsTheme: "Tema",
    settingsLanguage: "Idioma",
    settingsHelp: "Ajuda",
    settingsFeedback: "Enviar feedback",
    settingsLanguageAuto: "Automático",
    themeLight: "Claro",
    themeDark: "Escuro",
    themeSystem: "Sistema",
    greetingMorning: "Bom dia.",
    greetingAfternoon: "Boa tarde.",
    greetingEvening: "Boa noite.",
    greetingAfterHours: "Trabalhando até tarde?",
    greetingQuestion: "Como posso ajudar?",
    welcomeSub:
      "Pergunte sobre pagamentos, contratos, Canvas, alunos ou qualquer assunto dos guias do instrutor.",
    sendButton: "Enviar",
    regenerateButton: "Regenerar",
    stopButton: "Parar",
    copyButton: "Copiar",
    editButton: "Editar",
    editCancel: "Cancelar",
    editSave: "Salvar",
    thinkingDefault: "Pensando…",
    sourcesTitle: "Fontes",
    sourcesCountSingular: "{n} trecho citado",
    sourcesCountPlural: "{n} trechos citados",
    sourcesCloseAria: "Fechar fontes",
    sourcesOpenAria: "Abrir {n} fontes da resposta",
    sourceTypeGuide: "Guia do instrutor (PDF)",
    sourceTypeExternal: "Página externa · {host}",
    sourceFallbackTitle: "Fonte",
    sourceNumberAria: "Fonte {n}: {title}",
    opensInNewTab: "(abre em uma nova aba)",
    showMoreCitationOne: "Mostrar mais 1 citação",
    showMoreCitations: "Mostrar mais {n} citações",
    feedbackLoveTitle: "Adorei",
    feedbackNeedsImprovementTitle: "Precisa melhorar",
    feedbackPlaceholder:
      "O que teria tornado esta resposta mais útil para você?",
    feedbackCancelButton: "Cancelar",
    feedbackSubmitButton: "Enviar",
    feedbackThanksToast: "Obrigado pelo seu feedback!",
    gfDrawerTitle: "Enviar feedback",
    gfDrawerDescription:
      "Ajude-nos a melhorar o Assistente do Instrutor da BYU-Pathway. Conte-nos o que aconteceu e o que você esperava.",
    gfDrawerLabel: "Descreva seu feedback (obrigatório)",
    gfDrawerPlaceholder: "Conte-nos o que motivou este feedback...",
    gfDrawerSensitiveInfo:
      "Não inclua nomes, números de identificação ou notas de alunos, nem outras informações confidenciais.",
    gfDrawerCancel: "Cancelar",
    gfDrawerSend: "Enviar",
    gfDrawerSending: "Enviando...",
    gfDrawerCloseTitle: "Fechar",
    gfDrawerEmptyToast: "Por favor, descreva seu feedback antes de enviar.",
    gfDrawerSuccessToast: "Obrigado pelo seu feedback!",
    gfDrawerErrorToast: "Não foi possível enviar o feedback. Tente novamente.",
    draftSend: "Enviar",
    draftCopy: "Copiar",
    draftCopied: "Copiado!",
    draftOutlookWork: "Outlook (trabalho ou escola)",
    draftOutlookPersonal: "Outlook.com (pessoal)",
    draftAcceptOrUndo: "Aceitar ou desfazer?",
    draftAccept: "Aceitar",
    draftUndo: "Desfazer",
    draftTextStyle: "Estilo de texto: {style}",
    draftStyleText: "Texto",
    draftStyleH1: "Título 1",
    draftStyleH2: "Título 2",
    draftStyleH3: "Título 3",
    draftNumberedList: "Lista numerada",
    draftBulletedList: "Lista com marcadores",
    draftBold: "Negrito",
    draftItalic: "Itálico",
    draftUnderline: "Sublinhado",
    draftInsertLink: "Inserir link",
    draftTweak: "Ajustar",
    draftTweakPlaceholder: "Descreva a alteração que deseja fazer...",
    draftApply: "Aplicar",
    draftApplying: "Aplicando",
    draftLinkPlaceholder: "Cole um link...",
    draftInsert: "Inserir",
    draftLinkSelectFirstToast: "Selecione o texto que deseja transformar em link.",
    draftLinkInvalidUrlToast: "Insira um URL válido.",
    draftTweakErrorToast: "Por favor, reformule a solicitação.",
  },
};

export function getChromeStrings(lang: LangCode): ChromeStrings {
  return CHROME_STRINGS[lang] ?? CHROME_STRINGS.en;
}
