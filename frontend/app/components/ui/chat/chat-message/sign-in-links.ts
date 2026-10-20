// Links to pages behind a BYU-Pathway or BYU-Idaho sign-in. The backend labels
// each one "(sign-in required)" in the answer's language (CLAUDE.md §8.3);
// this only styles them: a lock icon on the link (markdown.tsx) and the label
// as a small gray note (the rehype plugin below).

// Mirrors the backend's default LOGIN_LINK_HOSTS (suffix match on a domain
// boundary, so "notsharepoint.com" doesn't count).
export const LOGIN_LINK_HOSTS = [
  "sharepoint.com",
  "companion.byupathway.edu",
  "pathwayadmin.byui.edu",
  "portal.byupathway.edu",
];

export function isLoginLink(href?: string): boolean {
  if (!href) return false;
  let host = "";
  try {
    host = new URL(href).hostname.toLowerCase();
  } catch {
    return false;
  }
  return LOGIN_LINK_HOSTS.some((h) => host === h || host.endsWith(`.${h}`));
}

// The note the backend appends: a short parenthetical right after the link,
// possibly after citation markers.
const NOTE_RE = /^(\s*)(\([^()\n]{1,40}\))/;

type HastNode = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: Record<string, unknown>;
  children?: HastNode[];
};

const textOf = (node: HastNode): string =>
  node.type === "text"
    ? node.value ?? ""
    : (node.children ?? []).map(textOf).join("");

const isCitation = (node: HastNode) =>
  node.type === "element" &&
  node.tagName === "a" &&
  /^citation(-group)?:/.test(textOf(node));

function wrapNotes(parent: HastNode) {
  const children = parent.children;
  if (!children) return;
  for (let i = 0; i < children.length; i++) {
    const child = children[i];
    if (child.type !== "element") continue;
    if (
      child.tagName === "a" &&
      isLoginLink(String(child.properties?.href ?? ""))
    ) {
      // Skip whitespace and citation markers to the first real text.
      let j = i + 1;
      while (
        j < children.length &&
        (isCitation(children[j]) ||
          (children[j].type === "text" && !children[j].value?.trim()))
      )
        j++;
      const next = children[j];
      const match = next?.type === "text" ? NOTE_RE.exec(next.value ?? "") : null;
      if (next && match) {
        const rest = (next.value ?? "").slice(match[0].length);
        const replacement: HastNode[] = [
          ...(match[1] ? [{ type: "text", value: match[1] }] : []),
          {
            type: "element",
            tagName: "span",
            properties: { className: ["signin-note"] },
            children: [{ type: "text", value: match[2] }],
          },
          ...(rest ? [{ type: "text", value: rest }] : []),
        ];
        children.splice(j, 1, ...replacement);
      }
      continue;
    }
    wrapNotes(child);
  }
}

// Runs after rehype-sanitize, so the class it adds survives.
export function rehypeSignInNotes() {
  return (tree: HastNode) => wrapNotes(tree);
}
