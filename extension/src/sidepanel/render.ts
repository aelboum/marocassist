/**
 * Render the side panel from a snapshot. Uses `textContent` only, never
 * `innerHTML`: page text is untrusted input and must never become markup.
 */

import type { PageSnapshot } from "../shared/contracts";

function element<K extends keyof HTMLElementTagNameMap>(
  doc: Document,
  tag: K,
  text?: string,
  className?: string,
): HTMLElementTagNameMap[K] {
  const node = doc.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function list(doc: Document, title: string, items: string[], testId: string): HTMLElement {
  const section = element(doc, "section");
  section.dataset.testid = testId;
  section.append(element(doc, "h2", title));
  const ul = element(doc, "ul");
  for (const item of items) ul.append(element(doc, "li", item));
  section.append(ul);
  return section;
}

export function renderSnapshot(root: HTMLElement, snapshot: PageSnapshot | null, now = Date.now()): void {
  const doc = root.ownerDocument;
  root.replaceChildren();
  if (snapshot === null) {
    root.append(element(doc, "p", "Open the local test page to see guidance here.", "muted"));
    return;
  }

  const header = element(doc, "header");
  header.append(element(doc, "h1", snapshot.title || snapshot.location));
  header.append(element(doc, "p", snapshot.location, "muted"));
  const age = Math.max(0, Math.round((now - snapshot.capturedAt) / 1000));
  const updated = element(doc, "p", `Updated ${age}s ago`, "muted");
  updated.dataset.testid = "updated";
  header.append(updated);
  root.append(header);

  if (snapshot.captchaPresent) {
    const note = element(
      doc,
      "p",
      "This page has a security check (CAPTCHA). Complete it yourself; MarocAssist never interacts with it.",
      "notice",
    );
    note.dataset.testid = "captcha";
    root.append(note);
  }
  if (snapshot.alerts.length > 0) root.append(list(doc, "Messages on the page", snapshot.alerts, "alerts"));
  if (snapshot.headings.length > 0) root.append(list(doc, "Sections", snapshot.headings, "headings"));

  const fields = snapshot.fields.map((f) => {
    const parts = [f.label || "(unlabelled field)", f.kind];
    if (f.required) parts.push("required");
    if (f.error) parts.push(`error: ${f.error}`);
    return parts.join(" · ");
  });
  root.append(list(doc, `Fields (${snapshot.fields.length})`, fields, "fields"));
  if (snapshot.buttons.length > 0) root.append(list(doc, "Buttons", snapshot.buttons, "buttons"));

  root.append(
    element(
      doc,
      "p",
      "MarocAssist only reads the page layout. It never fills in, submits or books anything for you.",
      "muted",
    ),
  );
}
