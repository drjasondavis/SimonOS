/**
 * Gmail content script — injects an "✨ Reply" button into every compose window.
 *
 * The button sends the full email context to the /reply endpoint, which
 * classifies the intent and dispatches to the right handler:
 *
 *   scheduling → suggests meeting times or creates a calendar event
 *   general    → drafts a contextually appropriate reply
 *
 * All handlers return { text, action_url, label, mode }:
 *   text       — inserted into the compose body at the cursor
 *   action_url — opened in a new tab if present (e.g. pre-filled Google Calendar)
 *   label      — shown on the button after completion
 *
 * Setup:
 *   1. Run the API server: uvicorn api.server:app --port 5556 --reload
 *   2. Load this extension unpacked in chrome://extensions
 *   3. Open Gmail and compose/reply — you'll see the ✨ Reply button
 */

const API_BASE = "http://127.0.0.1:5556";
const API_SECRET = "1cafeced5f5ecf39ba49dc7afe98994f"; // must match API_SECRET in .env

// ---------------------------------------------------------------------------
// Cursor tracking
// ---------------------------------------------------------------------------

const savedRanges = new WeakMap();

function saveRange(bodyEl) {
  const sel = window.getSelection();
  if (sel && sel.rangeCount > 0) {
    const range = sel.getRangeAt(0);
    if (bodyEl.contains(range.commonAncestorContainer)) {
      savedRanges.set(bodyEl, range.cloneRange());
    }
  }
}

function restoreAndInsert(bodyEl, text) {
  bodyEl.focus();
  const sel = window.getSelection();
  sel.removeAllRanges();

  const saved = savedRanges.get(bodyEl);
  if (saved) {
    sel.addRange(saved);
  } else {
    const r = document.createRange();
    r.selectNodeContents(bodyEl);
    r.collapse(false);
    sel.addRange(r);
  }

  document.execCommand("insertText", false, text);
  savedRanges.delete(bodyEl);
}

// ---------------------------------------------------------------------------
// Email content extraction (unchanged from cal-manager extension)
// ---------------------------------------------------------------------------

function getBodyEl(composeEl) {
  return (
    composeEl.querySelector('[role="textbox"][g_editable="true"]') ||
    composeEl.querySelector('[role="textbox"]')
  );
}

function getUserDraft(bodyEl) {
  const clone = bodyEl.cloneNode(true);
  clone.querySelectorAll(".gmail_quote, .gmail_signature").forEach((el) => el.remove());
  return clone.innerText.trim();
}

async function expandAllMessages() {
  const expanders = document.querySelectorAll(".ajR, .T-I.T-I-JO");
  expanders.forEach((btn) => { try { btn.click(); } catch (_) {} });
  if (expanders.length > 0) {
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
}

function getFullThread(composeEl) {
  const parts = [];
  const seen = new Set();

  function add(text) {
    const t = text.trim();
    if (t && !seen.has(t)) {
      seen.add(t);
      parts.push(t);
    }
  }

  document.querySelectorAll(".gs").forEach((msgEl) => {
    if (composeEl.contains(msgEl)) return;

    const senderEl = msgEl.querySelector(".gD");
    const senderName = senderEl?.getAttribute("name") || senderEl?.innerText || "";
    const senderEmail = senderEl?.getAttribute("email") || "";
    const sender = senderName && senderEmail
      ? `${senderName} <${senderEmail}>`
      : senderEmail || senderName;
    const date = msgEl.querySelector(".g3")?.innerText ||
                 msgEl.querySelector(".ads span")?.innerText || "";
    const header = [sender, date].filter(Boolean).join(" — ");

    const bodyEl = msgEl.querySelector(".ii .a3s") ||
                   msgEl.querySelector(".a3s.aiL") ||
                   msgEl.querySelector(".a3s") ||
                   msgEl.querySelector(".ii");

    const bodyText = bodyEl?.innerText.trim() || "";
    const text = bodyText || (msgEl.querySelector(".y2")?.innerText.trim() || "");
    if (text) {
      add(header ? `[${header}]\n${text}` : text);
    }
  });

  const composeBodyEl = getBodyEl(composeEl);
  if (composeBodyEl) {
    composeBodyEl.querySelectorAll(".gmail_quote").forEach((q) => {
      add(q.innerText || "");
    });
  }

  return parts.join("\n\n--- previous message ---\n\n");
}

function getThreadParticipants(composeEl) {
  const people = new Map();

  function add(email, name) {
    const e = (email || "").toLowerCase().trim();
    if (!e || !e.includes("@")) return;
    const n = (name || "").trim();
    if (!people.has(e) || (n && n.length > (people.get(e) || "").length)) {
      people.set(e, n);
    }
  }

  document.querySelectorAll(".gD[email]").forEach((el) => {
    add(el.getAttribute("email"), el.getAttribute("name") || el.innerText);
  });

  document.querySelectorAll(".vO [email], .aoD [email]").forEach((el) => {
    add(el.getAttribute("email"), el.getAttribute("name") || el.innerText);
  });

  return [...people.entries()].map(([email, name]) =>
    name ? `${name} <${email}>` : email
  );
}

// ---------------------------------------------------------------------------
// API call
// ---------------------------------------------------------------------------

async function callReply(emailBody, threadContext, subject = "", participants = []) {
  const res = await fetch(`${API_BASE}/reply`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Api-Secret": API_SECRET,
    },
    body: JSON.stringify({
      subject,
      email_body: emailBody,
      thread_context: threadContext,
      participants,
      duration_minutes: 60,
      days: 14,
    }),
  });
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  return res.json();
}

// ---------------------------------------------------------------------------
// Button
// ---------------------------------------------------------------------------

function createButton() {
  const btn = document.createElement("div");
  btn.className = "email-responder-btn";
  btn.setAttribute("role", "button");
  btn.title = "AI reply assistant — drafts a reply or suggests meeting times";
  btn.textContent = "✨ Reply";
  Object.assign(btn.style, {
    display: "inline-flex",
    alignItems: "center",
    padding: "6px 10px",
    margin: "0 4px",
    background: "#1a73e8",
    color: "white",
    borderRadius: "4px",
    cursor: "pointer",
    fontSize: "13px",
    fontFamily: "'Google Sans', Roboto, sans-serif",
    fontWeight: "500",
    userSelect: "none",
    whiteSpace: "nowrap",
  });
  return btn;
}

function findToolbar(composeEl) {
  const byRole = composeEl.querySelector('[role="toolbar"]');
  if (byRole) return byRole;

  for (const sel of [".btC", ".aDh", ".gU.Up", "td.gU"]) {
    const el = composeEl.querySelector(sel);
    if (el) return el;
  }

  const sendBtn = composeEl.querySelector(
    '[aria-label="Send"], [data-tooltip="Send"], [aria-label^="Send"]'
  );
  if (sendBtn) {
    let el = sendBtn.parentElement;
    while (el && el !== composeEl) {
      if (el.children.length > 2) return el;
      el = el.parentElement;
    }
  }

  return null;
}

function injectButton(composeEl) {
  if (composeEl.querySelector(".email-responder-btn")) return;

  const toolbar = findToolbar(composeEl);
  if (!toolbar) {
    console.log("[email-responder] toolbar not found", composeEl);
    return;
  }

  const bodyEl = getBodyEl(composeEl);
  if (!bodyEl) {
    console.log("[email-responder] body textbox not found", composeEl);
    return;
  }

  const btn = createButton();

  ["mouseup", "keyup", "click"].forEach((evt) => {
    bodyEl.addEventListener(evt, () => saveRange(bodyEl));
  });

  btn.addEventListener("mousedown", (e) => {
    e.preventDefault();
    saveRange(bodyEl);
  });

  btn.addEventListener("click", async () => {
    await expandAllMessages();
    const emailBody = getUserDraft(bodyEl);
    const threadContext = getFullThread(composeEl);
    const subject =
      composeEl.querySelector('[name="subjectbox"], [aria-label*="Subject"]')?.value ||
      document.querySelector("h2.hP")?.innerText || "";

    btn.textContent = "⏳ Thinking...";
    btn.style.pointerEvents = "none";

    try {
      const participants = getThreadParticipants(composeEl);
      const result = await callReply(emailBody, threadContext, subject, participants);

      // Insert the reply text at cursor
      if (result.text) {
        restoreAndInsert(bodyEl, result.text.trim());
      }

      // Open any action URL in a new tab (e.g. Google Calendar event creation)
      if (result.action_url) {
        window.open(result.action_url, "_blank");
      }

      btn.textContent = result.label || "✅ Done";
    } catch (err) {
      btn.textContent = "❌ Error";
      console.error("[email-responder]", err);
    } finally {
      setTimeout(() => {
        btn.textContent = "✨ Reply";
        btn.style.pointerEvents = "auto";
      }, 3000);
    }
  });

  toolbar.appendChild(btn);
}

// ---------------------------------------------------------------------------
// Watch for compose windows
// ---------------------------------------------------------------------------

function scanForComposeWindows() {
  const candidates = document.querySelectorAll(
    '[role="dialog"], .nH.Hd[aria-label], form[role="dialog"]'
  );
  candidates.forEach((el) => {
    const hasSubject =
      el.querySelector('[aria-label*="Subject"]') ||
      el.querySelector('[name="subjectbox"]') ||
      el.querySelector('input[aria-label*="Subject"]');
    if (hasSubject) {
      injectButton(el);
    }
  });

  document.querySelectorAll('.M9 [role="textbox"]').forEach((textbox) => {
    const composeRoot = textbox.closest(".M9, .dw, .aaZ");
    if (composeRoot && !composeRoot.querySelector(".email-responder-btn")) {
      injectButton(composeRoot);
    }
  });
}

const observer = new MutationObserver(scanForComposeWindows);
observer.observe(document.body, { childList: true, subtree: true });

scanForComposeWindows();
