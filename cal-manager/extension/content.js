/**
 * Gmail content script — injects a "📅 Scheduler" button into every compose window.
 *
 * Mode 1 — Suggest times (no agreed time in thread yet):
 *   Reads the email draft + thread context, sends to /schedule, gets back
 *   Claude-written suggestion text, and inserts it at the cursor.
 *
 * Mode 2 — Create event (other person has replied and agreed to a time):
 *   Sends the full thread to /schedule, Claude extracts event details,
 *   opens a pre-filled Google Calendar create page in a new tab, and
 *   inserts a short note at the cursor.
 *
 * Setup:
 *   1. Run the API server: uvicorn api.server:app --port 5555
 *   2. Load this extension unpacked in chrome://extensions
 *   3. Open Gmail and compose/reply — you'll see the 📅 button in the toolbar
 */

const API_BASE = "http://127.0.0.1:5555";
const API_SECRET = "change-me"; // must match API_SECRET in .env

// ---------------------------------------------------------------------------
// Cursor tracking
// ---------------------------------------------------------------------------

// Saved selection range per compose element (keyed by the textbox element)
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
    // Fall back to end of content
    const r = document.createRange();
    r.selectNodeContents(bodyEl);
    r.collapse(false);
    sel.addRange(r);
  }

  document.execCommand("insertText", false, text);
  savedRanges.delete(bodyEl);
}

// ---------------------------------------------------------------------------
// Email content extraction
// ---------------------------------------------------------------------------

function getBodyEl(composeEl) {
  return (
    composeEl.querySelector('[role="textbox"][g_editable="true"]') ||
    composeEl.querySelector('[role="textbox"]')
  );
}

/**
 * Returns just the user's draft text, excluding quoted prior messages.
 */
function getUserDraft(bodyEl) {
  const clone = bodyEl.cloneNode(true);
  clone.querySelectorAll(".gmail_quote, .gmail_signature").forEach((el) => el.remove());
  return clone.innerText.trim();
}

/**
 * Returns the full email thread — every message we can find, in order.
 *
 * Gmail renders each email in a thread as a .gs container. We iterate all of
 * them and extract:
 *   - Sender email/name and date from the message header
 *   - Full body text (expanded messages use .a3s; collapsed ones are
 *     display:none so we fall back to textContent to read hidden DOM)
 *
 * We also pull the quoted chain from inside the compose body as a fallback
 * for any messages not captured by the thread view selectors.
 */
/**
 * Click every "..." expander in the thread so Gmail renders the full content,
 * then wait long enough for the DOM to update before we read.
 *
 * Targets:
 *   .ajR  — "show trimmed content" button inside a message body
 *   .T-I.T-I-JO — collapsed message row expand button
 */
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

  // Walk every .gs element — each one is a single email in the thread.
  // Everything should be expanded now thanks to expandAllMessages().
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

    // Fall back to snippet for any message that still didn't expand
    const text = bodyText || (msgEl.querySelector(".y2")?.innerText.trim() || "");
    if (text) {
      add(header ? `[${header}]\n${text}` : text);
    }
  });

  // Also pull the quoted chain from the compose body as a safety net
  const composeBodyEl = getBodyEl(composeEl);
  if (composeBodyEl) {
    composeBodyEl.querySelectorAll(".gmail_quote").forEach((q) => {
      add(q.innerText || "");
    });
  }

  return parts.join("\n\n--- previous message ---\n\n");
}

/**
 * Collects all email addresses visible in the current thread — senders,
 * recipients, and CC'd addresses — so Claude can decide who belongs on
 * the invite. Deduplicates and excludes the current user's own address.
 */
function getThreadParticipants(composeEl) {
  const people = new Map(); // email → display name

  function add(email, name) {
    const e = (email || "").toLowerCase().trim();
    if (!e || !e.includes("@")) return;
    const n = (name || "").trim();
    // Keep the most informative name we find
    if (!people.has(e) || (n && n.length > (people.get(e) || "").length)) {
      people.set(e, n);
    }
  }

  // All .gD elements across the full thread (senders, To, CC)
  document.querySelectorAll(".gD[email]").forEach((el) => {
    const email = el.getAttribute("email");
    // Gmail stores display name in the `name` attribute or innerText
    const name = el.getAttribute("name") || el.innerText || "";
    add(email, name);
  });

  // Compose To: chip elements
  document.querySelectorAll(".vO [email], .aoD [email]").forEach((el) => {
    add(el.getAttribute("email"), el.getAttribute("name") || el.innerText);
  });

  // Format as "Name <email>" so Claude can use names for title generation
  return [...people.entries()].map(([email, name]) =>
    name ? `${name} <${email}>` : email
  );
}

// ---------------------------------------------------------------------------
// API call
// ---------------------------------------------------------------------------

async function callSchedule(emailBody, threadContext, subject = "", participants = []) {
  const res = await fetch(`${API_BASE}/schedule`, {
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
  btn.className = "cal-scheduler-btn";
  btn.setAttribute("role", "button");
  btn.title = "Suggest times or create a calendar event from this thread";
  btn.textContent = "📅 Scheduler";
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
  // Try role first, then Gmail's obfuscated class names, then fall back to
  // the send button's parent row (most reliable across Gmail versions).
  const byRole = composeEl.querySelector('[role="toolbar"]');
  if (byRole) return byRole;

  for (const sel of [".btC", ".aDh", ".gU.Up", "td.gU"]) {
    const el = composeEl.querySelector(sel);
    if (el) return el;
  }

  // Last resort: find the Send button and walk up to its toolbar row
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
  if (composeEl.querySelector(".cal-scheduler-btn")) return;

  const toolbar = findToolbar(composeEl);
  if (!toolbar) {
    console.log("[cal-scheduler] toolbar not found", composeEl);
    return;
  }

  const bodyEl = getBodyEl(composeEl);
  if (!bodyEl) {
    console.log("[cal-scheduler] body textbox not found", composeEl);
    return;
  }

  const btn = createButton();

  // Track cursor position whenever the user interacts with the compose body
  ["mouseup", "keyup", "click"].forEach((evt) => {
    bodyEl.addEventListener(evt, () => saveRange(bodyEl));
  });

  // Prevent button click from stealing focus (standard toolbar trick).
  // This keeps the cursor position in the compose body active.
  btn.addEventListener("mousedown", (e) => {
    e.preventDefault();
    saveRange(bodyEl); // snapshot the range right before focus could change
  });

  btn.addEventListener("click", async () => {
    await expandAllMessages();
    const emailBody = getUserDraft(bodyEl);
    const threadContext = getFullThread(composeEl);
    const subject = composeEl.querySelector('[name="subjectbox"], [aria-label*="Subject"]')?.value ||
                    document.querySelector('h2.hP')?.innerText || "";

    btn.textContent = "⏳ Thinking...";
    btn.style.pointerEvents = "none";

    try {
      const participants = getThreadParticipants(composeEl);
      const result = await callSchedule(emailBody, threadContext, subject, participants);

      if (result.mode === "create") {
        // Open the pre-filled Google Calendar event page in a new tab
        window.open(result.calendar_url, "_blank");
        restoreAndInsert(bodyEl, result.reply_text.trim());
        btn.textContent = "✅ Invite sent";
      } else {
        // Insert Claude-written suggestion text at the cursor
        restoreAndInsert(bodyEl, result.text.trim());
        btn.textContent = "✅ Inserted";
      }
    } catch (err) {
      btn.textContent = "❌ Error";
      console.error("[cal-scheduler]", err);
    } finally {
      setTimeout(() => {
        btn.textContent = "📅 Scheduler";
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
  // A compose window is any dialog (or inline compose) that contains a
  // Subject field AND a message body textbox.
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

  // Also look for inline compose (non-dialog compose at bottom of Gmail)
  document.querySelectorAll(".M9 [role=\"textbox\"]").forEach((textbox) => {
    const composeRoot = textbox.closest(".M9, .dw, .aaZ");
    if (composeRoot && !composeRoot.querySelector(".cal-scheduler-btn")) {
      injectButton(composeRoot);
    }
  });
}

const observer = new MutationObserver(scanForComposeWindows);
observer.observe(document.body, { childList: true, subtree: true });

// Run once on load in case compose is already open
scanForComposeWindows();
