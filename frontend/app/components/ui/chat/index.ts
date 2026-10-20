import { isValidUrl } from "../lib/utils";
import ChatInput from "./chat-input";
import ChatMessages from "./chat-messages";

export { type ChatHandler } from "./chat.interface";
export { ChatInput, ChatMessages };

// The annotation types the chat stream sends (backend/API.md), in arrival
// order: events, date_spans, user_language, sources, suggested_questions.
export enum MessageAnnotationType {
  EVENTS = "events",
  DATE_SPANS = "date_spans",
  USER_LANGUAGE = "user_language",
  SOURCES = "sources",
  SUGGESTED_QUESTIONS = "suggested_questions",
}

export type SourceNode = {
  id: string;
  citation_node_id: string;
  metadata: Record<string, unknown>;
  score?: number;
  text: string;
  url: string;
};

export type SourceData = {
  nodes: SourceNode[];
};

export type EventData = {
  title: string;
  isCollapsed: boolean;
};

export type SuggestedQuestionsData = string[];

export type UserLanguageData = {
  language: string;
};

export type DateSpansData = {
  phrases: string[];
  language?: string;
};

export type AnnotationData =
  | SourceData
  | EventData
  | DateSpansData
  | SuggestedQuestionsData
  | UserLanguageData;

export type MessageAnnotation = {
  type: MessageAnnotationType;
  data: AnnotationData;
  trace_id?: string;
};

export function getAnnotationData<T>(
  annotations: MessageAnnotation[],
  type: MessageAnnotationType,
): T[] {
  return annotations.filter((a) => a.type === type).map((a) => a.data as T);
}

// One processed copy per `sources` annotation object, so every render (and
// every consumer) gets the same object back: useMemo([data.nodes]) stays
// stable, and useChat's message objects are never modified.
const processedSources = new WeakMap<SourceData, SourceData>();

/**
 * The `sources` annotation, processed once and cached: nodes without a
 * usable URL are dropped and a trailing "/" is trimmed. Order is left alone
 * (every consumer sorts by citation number). Pure: the annotation itself is
 * not changed.
 */
export function getSourceAnnotationData(
  annotations: MessageAnnotation[],
): SourceData[] {
  return getAnnotationData<SourceData>(
    annotations,
    MessageAnnotationType.SOURCES,
  ).map((raw) => {
    if (!raw?.nodes) return raw;
    let processed = processedSources.get(raw);
    if (!processed) {
      processed = {
        ...raw,
        nodes: raw.nodes
          .filter((node) => isValidUrl(node.url))
          .map((node) => ({ ...node, url: node.url.replace(/\/$/, "") })),
      };
      processedSources.set(raw, processed);
    }
    return processed;
  });
}
