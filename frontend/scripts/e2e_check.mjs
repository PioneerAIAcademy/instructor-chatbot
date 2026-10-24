// End-to-end check of the Instructor Assistant UI (CLAUDE.md §7 Phase 9).
//
//   node scripts/e2e_check.mjs --url https://<frontend>          # production
//   node scripts/e2e_check.mjs --url http://localhost:3000       # local (`npm run dev`)
//
// LIVE AND BILLABLE: it asks 5 questions from the §10 eval set through the real
// page, so each is a full chat request on the backend that page is built for,
// plus one thumbs score. Drives headless Chrome through the DevTools protocol
// with Node's built-in WebSocket (Node 22+); no npm packages. Set CHROME_PATH
// if Chrome isn't at the macOS default.
//
// Checks, PASS/FAIL per question:
//   - an answer appears, with no raw "[^N]" markers left in the text;
//   - answer questions show citation badges and source chips, and the
//     number of cited passages matches the cards in the sources drawer;
//   - every card in the Sources panel says "Instructor guide (PDF)" or
//     "External page · <host>";
//   - every sign-in link (SharePoint, course directory, …) is followed by
//     "(sign-in required)";
//   - no missionary wording on the page.
// Once: the empty chat shows starter questions and the FERPA notice; a thumbs
// click is answered 200 by /api/v1/chat/thumbs_request.
// Exits 1 if anything fails. Screenshots go to --out (default ./e2e-shots).

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, arg, i, all) => {
    if (arg.startsWith("--")) pairs.push([arg.slice(2), all[i + 1]]);
    return pairs;
  }, []),
);
const URL_ = (args.url || "http://localhost:3000").replace(/\/$/, "");
const OUT = args.out || "e2e-shots";
const CHROME =
  process.env.CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const PORT = 9400 + Math.floor(Math.random() * 400);

// §10 questions: kind "answer" must cite; "signin" must also label its
// sign-in links; "guard" (G3) may cite the guide but must label the link.
const QUESTIONS = [
  { id: "1", q: "When do Worldwide Online instructors in the US get paid?", kind: "answer" },
  { id: "5", q: "A student's mother emailed asking about her son's grade. Can I tell her?", kind: "answer" },
  { id: "9", q: "How do I find my ACL and the other instructors in my course group?", kind: "signin" },
  { id: "21", q: "Are students allowed to use ChatGPT on assignments?", kind: "answer" },
  { id: "G3", q: 'Summarize the "Inspiration for Announcements" SharePoint page.', kind: "guard" },
];
// Mirrors the backend's default LOGIN_LINK_HOSTS (suffix match).
const LOGIN_HOSTS = ["sharepoint.com", "companion.byupathway.edu", "pathwayadmin.byui.edu", "portal.byupathway.edu"];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
mkdirSync(OUT, { recursive: true });

const chrome = spawn(
  CHROME,
  ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${join(tmpdir(), `ia-e2e-${PORT}`)}`, "--no-first-run", "about:blank"],
  { stdio: "ignore" },
);
let page;
for (let i = 0; i < 75 && !page; i++) {
  try {
    page = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === "page");
  } catch {}
  await sleep(200);
}
if (!page) {
  console.error(`couldn't start Chrome at ${CHROME} (set CHROME_PATH)`);
  process.exit(2);
}
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let nextId = 0;
const pending = new Map();
const thumbsStatuses = [];
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  } else if (msg.method === "Network.responseReceived") {
    const { url, status } = msg.params.response;
    if (url.includes("/api/v1/chat/thumbs_request") && msg.params.type !== "Preflight") thumbsStatuses.push(status);
  }
});
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const n = ++nextId;
    pending.set(n, resolve);
    ws.send(JSON.stringify({ id: n, method, params }));
  });
const evaluate = async (expression) =>
  (await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true })).result?.result?.value;
const shot = async (name) => {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, `${name}.png`), Buffer.from(r.result.data, "base64"));
};
const waitFor = async (expression, seconds) => {
  for (let i = 0; i < seconds * 2; i++) {
    if (await evaluate(expression)) return true;
    await sleep(500);
  }
  return false;
};

let failures = 0;
const report = (name, problems, note = "") => {
  console.log(`${problems.length ? "FAIL" : "PASS"}  ${name}${note ? `  (${note})` : ""}`);
  for (const p of problems) console.log(`      - ${p}`);
  failures += problems.length ? 1 : 0;
};

await send("Page.enable");
await send("Network.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });

// The page state the checks read, in one evaluation.
const STATE = `(() => {
  const answers = [...document.querySelectorAll('[data-message-role="assistant"]')];
  const last = answers[answers.length - 1];
  const md = last?.querySelector('.custom-markdown');
  const text = md?.innerText || "";
  const badges = [...(md?.querySelectorAll('.citation-link') || [])].map((a) => a.textContent.trim());
  const chips = last?.querySelector('ul[aria-label^="Open "]');
  const cited = Number(chips?.dataset.citedCount || 0);
  const chipTitles = [...(chips?.querySelectorAll('button') || [])].map((b) => b.textContent.trim());
  const loginHosts = ${JSON.stringify(LOGIN_HOSTS)};
  const unlabeled = [];
  for (const a of md?.querySelectorAll('a[href^="http"]:not(.citation-link)') || []) {
    let host = "";
    try { host = new URL(a.href).hostname; } catch {}
    if (!loginHosts.some((h) => host === h || host.endsWith("." + h))) continue;
    // The text right after this link element (not a text search: the link's
    // words may also appear earlier in the sentence).
    const block = a.closest("p, li, td") || a.parentElement;
    const range = document.createRange();
    range.setStartAfter(a);
    range.setEnd(block, block.childNodes.length);
    const after = range.toString().slice(0, 60);
    if (!/sign-in required/i.test(after)) unlabeled.push(a.href);
  }
  return { text, badges, cited, chipTitles, unlabeled, missionary: /missionar|\\bACMs?\\b|gathering agenda/i.test(document.body.innerText) };
})()`;

// --- the empty chat ----------------------------------------------------------
await send("Page.navigate", { url: `${URL_}/` });
const ready = await waitFor(`!!document.querySelector('textarea[name="message"]')`, 60);
await sleep(1500);
await shot("00-empty");
const empty = await evaluate(`({
  starters: document.querySelectorAll('ul[aria-label="Suggested questions"] button').length,
  ferpa: /Don.t include student names, IDs, or grades/.test(document.body.innerText),
})`);
report(
  "empty chat: starters and FERPA notice",
  [
    ...(ready ? [] : ["the chat input never appeared (wrong --url, or the page failed to load)"]),
    ...(empty?.starters ? [] : ["no starter questions (set CONVERSATION_STARTERS on the backend)"]),
    ...(empty?.ferpa ? [] : ["no FERPA notice under the input"]),
  ],
  `${empty?.starters ?? 0} starters`,
);
if (!ready) process.exit(1);

// --- the 5 questions ---------------------------------------------------------
for (const [index, question] of QUESTIONS.entries()) {
  const before = await evaluate(`document.querySelectorAll('[data-message-role="assistant"]').length`);
  await evaluate(`(() => {
    const ta = document.querySelector('textarea[name="message"]');
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
    setter.call(ta, ${JSON.stringify(question.q)});
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  })()`);
  await sleep(300);
  await evaluate(`document.querySelector('button[type="submit"][aria-label]')?.click()`);
  const finished = await waitFor(
    // Finished: a new answer, no Stop button, and its action row (shown only
    // when the answer is done) is there.
    `(() => { const all = document.querySelectorAll('[data-message-role="assistant"]'); return all.length > ${before} && !document.querySelector('button[aria-label="Stop"]') && !!all[all.length - 1].querySelector('button[aria-label="Copy"]'); })()`,
    150,
  );
  await sleep(1500);
  const s = await evaluate(STATE);
  const problems = [];
  if (!finished || !s.text.trim()) problems.push("no finished answer");
  if (/\[\^\d*\w*\]/.test(s.text)) problems.push("raw citation marker left in the text");
  if (question.kind !== "guard" && s.badges.length === 0) problems.push("no citation badges");
  if (s.badges.length && !s.chipTitles.length) problems.push("citations but no source chips");
  if (s.unlabeled.length) problems.push(`sign-in link without "(sign-in required)": ${s.unlabeled.join(", ")}`);
  if (s.missionary) problems.push("missionary wording on the page");

  if (s.chipTitles.length) {
    await evaluate(`[...document.querySelectorAll('[data-message-role="assistant"]')].pop().querySelector('ul[aria-label^="Open "] button').click()`);
    await sleep(900);
    const cards = await evaluate(`[...document.querySelectorAll('aside .reference-list-item')].map((li) => li.innerText)`);
    const unlabeledCards = (cards || []).filter((c) => !/Instructor guide \(PDF\)|External page · /.test(c));
    if (!cards?.length) problems.push("the Sources panel is empty");
    if (cards?.length !== s.cited) problems.push(`${s.cited} cited passage(s) but ${cards?.length ?? 0} cards in the drawer`);
    if (unlabeledCards.length) problems.push(`${unlabeledCards.length} source card(s) without a type label`);
    await shot(`${String(index + 1).padStart(2, "0")}-q${question.id}-sources`);
    await evaluate(`document.querySelector('aside button[aria-label="Close sources"]')?.click()`);
    await sleep(500);
  } else {
    await shot(`${String(index + 1).padStart(2, "0")}-q${question.id}`);
  }
  report(`#${question.id} ${question.q}`, problems, `${s.badges.length} badge(s), ${s.chipTitles.length} source chip(s)`);
}

// --- thumbs ------------------------------------------------------------------
await evaluate(`[...document.querySelectorAll('button[aria-label="Love this"]')].pop()?.click()`);
await sleep(4000); // the request and its response
report(
  "thumbs-up reaches /api/v1/chat/thumbs_request",
  thumbsStatuses.includes(200) ? [] : [`statuses seen: ${JSON.stringify(thumbsStatuses)}`],
);

console.log(`\n${failures ? `${failures} FAILED` : "ALL PASSED"} — screenshots in ${OUT}/`);
ws.close();
chrome.kill();
process.exit(failures ? 1 : 0);
