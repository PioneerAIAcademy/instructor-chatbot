/**
 * Registry for the draft the user is currently editing.
 *
 * WHY THIS EXISTS. `DraftComposer` renders the RTF draft in a `contentEditable`
 * div, so the user's edits live only in that node's DOM. The chat input is a
 * sibling component with no access to it, and `useChat` sends nothing but the
 * message history — so before this registry the model literally never received
 * what the user typed into the draft. Measured consequence (Langfuse session
 * 6d05f93d, 2026-08-19): asked to "review the slight changes I have made", the
 * model produced a confident three-point review of edits it had never been
 * sent, assembling it from the user's own earlier request text. The user replied
 * "You removed my adjustments."
 *
 * WHY A MODULE-LEVEL REGISTRY rather than context or a store. The composer is
 * mounted deep inside the memoized markdown subtree (`markdown.tsx` renders it
 * per code block), and threading a callback down would break the `React.memo`
 * that keeps streaming cheap — the profiling note in `chat-section.tsx` explains
 * how load-bearing that memoization is. The composer registers a getter on
 * mount; `chat-section` pulls a snapshot at submit time. Same "read LIVE state
 * at call time via a ref" shape the request builders there already use.
 *
 * ONLY DIRTY DRAFTS ARE REPORTED. An untouched draft is already in the message
 * history verbatim, so sending it again would just duplicate tokens. The dirty
 * flag is what makes the payload mean "the user changed this".
 */

export interface DraftSnapshot {
  draftType: "email" | "message";
  subject: string;
  body: string;
}

interface DraftSource {
  getSnapshot: () => DraftSnapshot | null;
  isDirty: () => boolean;
}

/**
 * Last composer to mount wins. A conversation can hold several drafts, but only
 * the newest is the one being worked on, and mount order follows message order.
 */
let activeSource: DraftSource | null = null;

export function registerDraftSource(source: DraftSource): () => void {
  activeSource = source;
  return () => {
    // Only clear if we are still the active source: a newer composer may have
    // registered before this one unmounted, and it must not be evicted.
    if (activeSource === source) {
      activeSource = null;
    }
  };
}

/**
 * The user's edited draft, or null when there is nothing to report — no draft
 * mounted, or mounted but untouched.
 */
export function getEditedDraftSnapshot(): DraftSnapshot | null {
  if (!activeSource || !activeSource.isDirty()) return null;

  const snapshot = activeSource.getSnapshot();
  if (!snapshot) return null;
  if (!snapshot.body.trim() && !snapshot.subject.trim()) return null;

  return snapshot;
}

/**
 * Per-draft edit store — survives the DraftComposer being REMOUNTED.
 *
 * WHY THIS IS SEPARATE FROM THE DIRTY REF. When a new turn is appended, useChat
 * hands the earlier assistant message a fresh object reference during streaming;
 * `memo(ChatMessage)` then re-renders it, ReactMarkdown rebuilds its subtree, and
 * the draft's `contentEditable` is replaced by a brand-new DOM node (verified: a
 * stamped node does not survive). A fresh mount resets the component's
 * `isDirtyRef` and re-hydrates from the `content` prop — silently wiping an
 * in-place edit. The composer's own dirty guard cannot help: it is per-instance
 * state, and the instance is exactly what was destroyed.
 *
 * So the edit has to live OUTSIDE the component. The composer saves each edit
 * here keyed by (message id + original draft text); on its next mount it looks
 * itself up and restores. The key includes the original content so a regenerate
 * (same message id, new draft) does not resurrect a stale edit, and so two
 * distinct drafts never collide.
 */
const editStore = new Map<string, DraftSnapshot>();

export function draftEditKey(messageId: string | undefined, content: string): string {
  return `${messageId ?? "nomsg"}::${content}`;
}

export function saveDraftEdit(key: string, snapshot: DraftSnapshot): void {
  editStore.set(key, snapshot);
}

export function getDraftEdit(key: string): DraftSnapshot | null {
  return editStore.get(key) ?? null;
}

/** Test seam. */
export function __resetDraftRegistry(): void {
  activeSource = null;
  editStore.clear();
}
