import { BookOpen, ExternalLink, FileText, Globe, X } from "lucide-react";
import { MouseEvent, useEffect, useMemo, useRef, useState } from "react";

import { getChromeStrings, type ChromeStrings } from "../../../../lib/chrome-strings";
import { resolveUiLanguage } from "../../../../lib/i18n";
import { useChromeStrings } from "../../../../lib/use-chrome-strings";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "../../hover-card";
import { cn } from "../../lib/utils";
import { SourceData, SourceNode } from "../index";

export const SOURCES_PANEL_EVENT = "pathway:sources-panel";

export type SourcesPanelEventDetail = {
  open: boolean;
  nodes?: SourceNode[];
  groupId?: string;
  // Positions (in citation order) of the sources the answer cites. The drawer
  // lists only these, numbered as their citations are.
  citedIndices?: number[];
};

const METADATA_TITLE_KEYS = [
  "title_tag",
  "logical_doc_label",
  "title",
  "page_title",
  "document_title",
  "source_title",
  "file_name",
  "name",
];

const MAX_SNIPPET_LENGTH = 230;

const getCitationNumber = (node: SourceNode) =>
  parseInt(node.citation_node_id.match(/^\d+/)?.[0] || "0", 10);

export const getSortedSources = (nodes: SourceNode[] = []) =>
  nodes.slice().sort((a, b) => getCitationNumber(a) - getCitationNumber(b));

/**
 * Which sources an answer cites: the positions, in getSortedSources order,
 * of the nodes its [^N] markers point at (Markdown maps markers the same
 * way). The backend sends every retrieved node; only the cited ones back the
 * answer.
 */
export const getCitedIndices = (answer: string, sorted: SourceNode[]) => {
  const indices = new Set<number>();
  for (const match of (answer || "").matchAll(/\[\^(\d+)\]/g)) {
    const number = parseInt(match[1], 10);
    const index = sorted.findIndex((node) => getCitationNumber(node) === number);
    if (index >= 0) indices.add(index);
  }
  return Array.from(indices).sort((a, b) => a - b);
};

// The instructor guides are `source=instructor-assistant`; the public pages
// they link to are `instructor-assistant-linked` (CLAUDE.md §1, §8.3).
export const isExternalSource = (node?: SourceNode) =>
  node?.metadata?.source === "instructor-assistant-linked";

/** "Instructor guide (PDF)" or "External page · <host>" (CLAUDE.md §8.3). */
export const getSourceTypeLabel = (
  node: SourceNode | undefined,
  strings: ChromeStrings,
) =>
  isExternalSource(node)
    ? strings.sourceTypeExternal.replace("{host}", getSourceDomain(node?.url))
    : strings.sourceTypeGuide;

export const buildSourcesGroupId = (nodes: SourceNode[] = []) => {
  if (nodes.length === 0) return "";
  return nodes[0].id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 16);
};

const safeUrl = (url?: string) => {
  if (!url) return null;
  try {
    return new URL(url);
  } catch {
    return null;
  }
};

export const getSourceDomain = (url?: string) => {
  const parsedUrl = safeUrl(url);
  if (!parsedUrl) return "Source";
  return parsedUrl.hostname.replace(/^www\./, "");
};

const prettifyDomain = (domain: string) => {
  if (!domain || domain === "Source") return "Source";
  const parts = domain.split(".");
  const brand = parts.length > 2 ? parts.at(-2) || domain : parts[0];
  return brand
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const titleFromUrl = (url?: string) => {
  const parsedUrl = safeUrl(url);
  if (!parsedUrl) return "";
  const lastPathSegment = parsedUrl.pathname.split("/").filter(Boolean).at(-1);
  if (!lastPathSegment) return prettifyDomain(getSourceDomain(url));
  return decodeURIComponent(lastPathSegment)
    .replace(/\.(html|pdf|aspx?)$/i, "")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
};

const normalizeSourceTitle = (value: string) => {
  return (
    value
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\bBYU\s*[- ]?\s*Pathway\b/gi, "BYU-Pathway")
      .replace(/\bBYU\s*[- ]?\s*Idaho\b/gi, "BYU-Idaho")
      .replace(/\bByupathway\b/gi, "BYU-Pathway")
      // Strip the trailing " | <Site>" SEO title suffix so a page title like
      // "Course Drops and Withdrawals | BYU-Pathway Worldwide" doesn't carry the
      // site name into the citation chip. Matches the final pipe-segment when it
      // contains a known BYU-Pathway-family site name (tolerates a trailing
      // "Worldwide"/"Online" etc.); [^|]* keeps it to the LAST segment only.
      .replace(
        /\s*\|\s*[^|]*\b(?:BYU-Pathway|BYU-Idaho|EnglishConnect|Ensign College)\b[^|]*$/i,
        "",
      )
      .trim()
  );
};

// Page CHROME that some crawled pages use as their <title> (a call-to-action
// prompt or a bare site name), which makes a poor citation source label. When a
// source's metadata title is chrome, skip it and fall back to the URL-derived
// title (e.g. byupathway.edu/help-faqs -> "Help Faqs"). This is the source-label
// side of the same fix that strips the CTA header from retrieved chunk TEXT.
const isChromeSourceTitle = (value: string) => {
  const v = value.trim();
  if (!v) return true;
  if (/^Have\s+(any\s+questions|a\s+question)\b.*\bhelp\b/i.test(v))
    return true;
  if (/^(BYU-Pathway|BYU-Idaho|EnglishConnect|Ensign College)$/i.test(v))
    return true;
  return false;
};

export const getSourceTitle = (node?: SourceNode) => {
  if (!node) return "Source";

  for (const key of METADATA_TITLE_KEYS) {
    const value = node.metadata?.[key];
    if (typeof value === "string") {
      const cleanValue = normalizeSourceTitle(value);
      if (
        cleanValue &&
        !/^https?:\/\//i.test(cleanValue) &&
        !isChromeSourceTitle(cleanValue)
      ) {
        return cleanValue;
      }
    }
  }

  return (
    normalizeSourceTitle(titleFromUrl(node.url)) ||
    normalizeSourceTitle(prettifyDomain(getSourceDomain(node.url)))
  );
};

const truncateText = (value: string, maxLength: number) => {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1).trimEnd()}...`;
};


export const getSourceSnippet = (
  node?: SourceNode,
  maxLength = MAX_SNIPPET_LENGTH,
) => {
  const text = (node?.text || "")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();

  if (!text) return "";

  const sentence =
    text.match(/.{80,}?[.!?](?:\s|$)/)?.[0]?.trim() ||
    text.match(/[^.!?]+[.!?]/)?.[0]?.trim() ||
    text;

  return truncateText(sentence, maxLength);
};

const highlightReferenceListItem = (
  groupId: string | undefined,
  index: number,
  shouldHighlight: boolean,
) => {
  if (!groupId) return;
  const selector = `.reference-list-item[data-citation-group="${groupId}"][data-citation-index="${index}"]`;
  document
    .querySelectorAll(selector)
    .forEach((item) =>
      item.classList.toggle("citation-hovered", shouldHighlight),
    );
};

// The small round icon in citation pills and source rows. Upstream showed the
// site's favicon from google.com/s2/favicons, which sent Google every cited
// domain; this shows a local icon by source type instead, in the same circle.
function SourceFavicon({
  node,
  className,
}: {
  node?: SourceNode;
  className?: string;
  size?: number;
}) {
  const Icon = isExternalSource(node) ? Globe : FileText;
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-white text-[#454540] ring-1 ring-black/10 dark:bg-[#2f302d] dark:text-[#ECEBE7] dark:ring-white/10",
        className,
      )}
    >
      <Icon aria-hidden="true" className="h-[70%] w-[70%]" />
    </span>
  );
}

// A small gray icon button in the answer's action row (copy, thumbs,
// regenerate): 40px on phones for touch, 32px up.
export const ACTION_BUTTON =
  "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg p-0 text-ia-muted transition-colors " +
  "hover:bg-ia-surface hover:text-ia-text sm:h-8 sm:w-8 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";

/**
 * The guides an answer cites, as chips under its text (one per document,
 * in citation order). Clicking one opens the sources panel. An answer that
 * cites nothing (a refusal, "not in the guides") gets no chips.
 */
export function ChatSources({ data, answer }: { data: SourceData; answer: string }) {
  const [uiLang, setUiLang] =
    useState<ReturnType<typeof resolveUiLanguage>>("en");
  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);
  const strings = getChromeStrings(uiLang);
  const sortedSources = useMemo(
    () => getSortedSources(data.nodes),
    [data.nodes],
  );
  const groupId = useMemo(
    () => buildSourcesGroupId(sortedSources),
    [sortedSources],
  );
  const citedIndices = useMemo(
    () => getCitedIndices(answer, sortedSources),
    [answer, sortedSources],
  );
  // Several cited passages can come from one guide: one chip per document.
  const documents = useMemo(() => {
    const seen = new Map<string, { node: SourceNode; title: string }>();
    for (const index of citedIndices) {
      const node = sortedSources[index];
      const title = getSourceTitle(node);
      const key = node.url || title;
      if (!seen.has(key)) seen.set(key, { node, title });
    }
    return Array.from(seen.values());
  }, [citedIndices, sortedSources]);

  if (documents.length === 0) return null;

  const openSourcesPanel = () => {
    window.dispatchEvent(
      new CustomEvent<SourcesPanelEventDetail>(SOURCES_PANEL_EVENT, {
        detail: {
          open: true,
          nodes: sortedSources,
          groupId,
          citedIndices,
        },
      }),
    );
  };

  return (
    <ul
      className="flex flex-wrap gap-2"
      aria-label={strings.sourcesOpenAria.replace(
        "{n}",
        String(citedIndices.length),
      )}
      data-cited-count={citedIndices.length}
    >
      {documents.map(({ node, title }) => {
        const Icon = isExternalSource(node) ? Globe : FileText;
        return (
          <li key={node.url || title} className="flex max-w-full">
            <button
              type="button"
              onClick={openSourcesPanel}
              title={`${title} · ${getSourceTypeLabel(node, strings)}`}
              className="inline-flex h-10 max-w-full items-center gap-1.5 rounded-lg border border-ia-line bg-ia-page px-2.5 text-[13px] font-semibold text-ia-body transition-colors hover:border-ia-gold hover:bg-ia-gold-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 sm:h-8"
            >
              <Icon className="h-3.5 w-3.5 shrink-0 text-ia-gold-ink" aria-hidden="true" />
              <span className="truncate">{title}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function CitationPopoverContent({
  node,
  index,
}: {
  node?: SourceNode;
  index: number;
}) {
  const title = getSourceTitle(node);
  const domain = getSourceTypeLabel(node, getChromeStrings(resolveUiLanguage()));
  const snippet = getSourceSnippet(node, 190);

  return (
    <a
      href={node?.url || "#"}
      target={node?.url ? "_blank" : undefined}
      rel={node?.url ? "noopener noreferrer" : undefined}
      className={[
        "block cursor-pointer rounded-xl px-3.5 py-3 text-left no-underline",
        "transition-colors duration-150 hover:bg-black/[0.045]",
        "dark:hover:bg-white/[0.07]",
      ].join(" ")}
    >
      <div className="flex items-start gap-3">
        <SourceFavicon node={node} className="mt-0.5 h-5 w-5" size={32} />
        <div className="min-w-0">
          <p className="line-clamp-2 text-[13px] font-semibold leading-[18px] text-[#2C2C29] dark:text-[#FCFCFC]">
            {title || `${getChromeStrings(resolveUiLanguage()).sourceFallbackTitle} ${index + 1}`}
          </p>
          {snippet && (
            <p className="mt-1.5 line-clamp-3 text-[12px] leading-[18px] text-[#5F5E59] dark:text-[#C6C6C2]">
              {snippet}
            </p>
          )}
          <div className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-[#73726C] dark:text-[#AFAFA9]">
            <span className="truncate">{domain}</span>
            {node?.url && <ExternalLink className="h-3 w-3 shrink-0" />}
          </div>
        </div>
      </div>
    </a>
  );
}

// The inline citation: a small numbered badge in BYU gold with a near-black
// number (10.4:1); a deeper gold when hovered or focused.
const CITE_BADGE =
  "citation-link mx-[2px] inline-flex h-[22px] min-w-[22px] items-center justify-center rounded-full px-[6px] align-[1px] " +
  "bg-ia-gold text-[11.5px] font-bold leading-none text-ia-on-gold no-underline " +
  "transition-colors duration-150 hover:bg-[#E0A400] " +
  "focus-visible:bg-[#E0A400] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2";

export function SourceNumberButton({
  index,
  className,
  node,
  url,
  groupId,
}: {
  index: number;
  className?: string;
  node?: SourceNode;
  url?: string;
  groupId?: string;
}) {
  const sourceNode =
    node ?? (url ? ({ url, metadata: {}, text: "" } as SourceNode) : undefined);
  const sourceUrl = sourceNode?.url || url;
  const title = getSourceTitle(sourceNode);
  const strings = useChromeStrings();
  const badgeLabel =
    strings.sourceNumberAria
      .replace("{n}", String(index + 1))
      .replace("{title}", title) + (sourceUrl ? ` ${strings.opensInNewTab}` : "");

  const handleMouseEnter = () =>
    highlightReferenceListItem(groupId, index, true);
  const handleMouseLeave = () =>
    highlightReferenceListItem(groupId, index, false);

  const badge = (
    <a
      href={sourceUrl || "#"}
      target={sourceUrl ? "_blank" : undefined}
      rel={sourceUrl ? "noopener noreferrer" : undefined}
      className={cn(CITE_BADGE, className)}
      aria-label={badgeLabel}
      data-citation-index={index}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
    >
      {index + 1}
    </a>
  );

  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>{badge}</HoverCardTrigger>
      <HoverCardContent
        side="top"
        align="start"
        className="w-[min(360px,calc(100vw-32px))] rounded-xl border-black/10 bg-white p-0 shadow-[0_18px_45px_rgba(0,0,0,0.18)] dark:border-white/[0.12] dark:bg-[#2F302D] dark:shadow-[0_18px_50px_rgba(0,0,0,0.55)]"
      >
        <CitationPopoverContent node={sourceNode} index={index} />
      </HoverCardContent>
    </HoverCard>
  );
}

/**
 * Several citations at one spot. Up to three show as badges side by side;
 * more collapse to the first badge plus a "+N" badge that expands them.
 */
export function CitationGroupPill({
  indices,
  sources,
  groupId,
}: {
  indices: number[];
  sources: SourceNode[];
  groupId?: string;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const strings = useChromeStrings();
  const validIndices = indices.filter((index) => sources[index]);

  if (validIndices.length === 0) return null;

  const shown = isExpanded || validIndices.length <= 3 ? validIndices : validIndices.slice(0, 1);
  const hidden = validIndices.length - shown.length;

  const expandGroup = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsExpanded(true);
  };

  return (
    <span className="inline-flex max-w-full flex-wrap items-center gap-y-1 align-baseline">
      {shown.map((index) => (
        <SourceNumberButton
          key={index}
          index={index}
          node={sources[index]}
          groupId={groupId}
        />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          onClick={expandGroup}
          className={CITE_BADGE}
          aria-label={
            hidden === 1
              ? strings.showMoreCitationOne
              : strings.showMoreCitations.replace("{n}", String(hidden))
          }
          aria-expanded={false}
        >
          +{hidden}
        </button>
      )}
    </span>
  );
}

export function SourcesSidebar({
  open,
  nodes,
  groupId,
  citedIndices,
  onClose,
}: {
  open: boolean;
  nodes: SourceNode[];
  groupId?: string;
  citedIndices?: number[];
  onClose: () => void;
}) {
  const sortedAll = useMemo(() => getSortedSources(nodes), [nodes]);
  // Only the cited sources, each keeping its position (= its citation number).
  const listed = useMemo(() => {
    const entries = sortedAll.map((node, index) => ({ node, index }));
    if (!citedIndices) return entries;
    const cited = new Set(citedIndices);
    return entries.filter((entry) => cited.has(entry.index));
  }, [sortedAll, citedIndices]);
  const asideRef = useRef<HTMLElement>(null);
  const [uiLang, setUiLang] =
    useState<ReturnType<typeof resolveUiLanguage>>("en");
  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);
  const strings = getChromeStrings(uiLang);
  const passagesTemplate =
    listed.length === 1
      ? strings.sourcesCountSingular
      : strings.sourcesCountPlural;
  const passagesLabel = passagesTemplate.replace(
    "{n}",
    String(listed.length),
  );

  // Escape closes the drawer.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Toggle the `inert` attribute imperatively. React 18 has no typed `inert`
  // prop and silently drops `inert=""`, so it must be set on the DOM node.
  // When the drawer is closed it is off-screen (translate-x-full) but its
  // links/buttons stay focusable — Tab focus lands inside it, the browser
  // scrolls it into view, and the chat content shifts left leaving a large
  // empty gap on the right. `inert` removes the whole closed subtree from
  // the tab order and from pointer interaction.
  useEffect(() => {
    const node = asideRef.current;
    if (!node) return;
    if (open) {
      node.removeAttribute("inert");
    } else {
      node.setAttribute("inert", "");
    }
  }, [open]);

  return (
    <aside
      ref={asideRef}
      className={cn(
        "absolute right-0 top-0 z-30 flex h-full w-[min(432px,calc(100vw-16px))] flex-col",
        "border-l border-black/10 bg-[#FAF9F5] shadow-[-18px_0_55px_rgba(0,0,0,0.16)]",
        "transition-[transform,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
        "dark:border-white/10 dark:bg-[#111210] dark:shadow-[-18px_0_55px_rgba(0,0,0,0.48)]",
        open
          ? "translate-x-0 opacity-100"
          : "pointer-events-none translate-x-full opacity-0",
      )}
      aria-hidden={!open}
      aria-label={strings.sourcesTitle}
    >
      <div className="flex items-center justify-between gap-3 border-b border-black/10 px-5 py-4 dark:border-white/10">
        <div className="flex min-w-0 items-center gap-2.5">
          <BookOpen className="h-5 w-5 shrink-0 text-[#3D3D3A] dark:text-[#FCFCFC]" />
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold leading-5 text-[#242421] dark:text-[#FCFCFC]">
              {strings.sourcesTitle}
            </h2>
            <p className="text-[12px] leading-4 text-[#73726C] dark:text-[#A7A6A0]">
              {passagesLabel}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className={[
            "inline-flex h-9 w-9 items-center justify-center rounded-full",
            "text-[#73726C] transition hover:bg-black/[0.06] hover:text-[#242421]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
            "dark:text-[#A7A6A0] dark:hover:bg-white/[0.08] dark:hover:text-[#FCFCFC]",
          ].join(" ")}
          aria-label={strings.sourcesCloseAria}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <div className="space-y-1">
          {listed.map(({ node, index }) => {
            const title = getSourceTitle(node);
            const domain = getSourceTypeLabel(node, strings);
            const snippet = getSourceSnippet(node);

            return (
              <a
                key={`${node.id}-${index}`}
                href={node.url}
                target="_blank"
                rel="noopener noreferrer"
                data-citation-group={groupId}
                data-citation-index={index}
                className={[
                  "reference-list-item group block rounded-xl px-3 py-3 no-underline",
                  "transition-colors duration-150 hover:bg-black/[0.045]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring",
                  "dark:hover:bg-white/[0.07]",
                ].join(" ")}
              >
                <div className="flex gap-3">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ia-gold text-[12px] font-bold text-ia-on-gold">
                    {index + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start gap-2">
                      <h3 className="line-clamp-2 flex-1 text-[13px] font-semibold leading-[18px] text-[#242421] group-hover:underline dark:text-[#FCFCFC]">
                        {title || `${getChromeStrings(resolveUiLanguage()).sourceFallbackTitle} ${index + 1}`}
                      </h3>
                      <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#8B8982] opacity-0 transition-opacity group-hover:opacity-100 dark:text-[#B6B5AF]" />
                    </div>
                    {snippet && (
                      <p className="mt-1.5 line-clamp-3 text-[12.5px] leading-[19px] text-[#55544F] dark:text-[#C7C7C3]">
                        {snippet}
                      </p>
                    )}
                    <div className="mt-2 flex items-center gap-1.5 text-[11px] font-medium text-[#73726C] dark:text-[#A7A6A0]">
                      <SourceFavicon node={node} className="h-3.5 w-3.5" />
                      <span className="truncate">{domain}</span>
                    </div>
                  </div>
                </div>
              </a>
            );
          })}
        </div>
      </div>
    </aside>
  );
}
