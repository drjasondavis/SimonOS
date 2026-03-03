/**
 * Gmail content script — injects a "Suggest Times" button into every
 * compose window. Clicking it fetches available slots from the local
 * Cal Manager API and inserts them as formatted text into the email body.
 *
 * Setup:
 *   1. Run the API server: uvicorn api.server:app --port 5555
 *   2. Load this extension unpacked in chrome://extensions
 *   3. Open Gmail and click Compose — you'll see the 📅 button in the toolbar
 */

const API_BASE = "http://localhost:5555";
const API_SECRET = "change-me"; // must match API_SECRET in .env
const DEFAULT_DURATION = 60;    // minutes

async function fetchSlots(durationMinutes = DEFAULT_DURATION) {
  const res = await fetch(
    `${API_BASE}/available-slots?duration=${durationMinutes}&days=7`,
    { headers: { "X-Api-Secret": API_SECRET } }
  );
  if (!res.ok) throw new Error(`API returned ${res.status}`);
  const { slots } = await res.json();
  return slots;
}

function formatSlotsText(slots) {
  if (!slots.length) {
    return "I don't have any availability in the next 7 days — let me know what works for you.";
  }
  const lines = slots.map((s, i) => `${i + 1}. ${s.display}`);
  return (
    "Here are a few times that work for me:\n\n" +
    lines.join("\n") +
    "\n\nLet me know which works best, or feel free to suggest an alternative!"
  );
}

function insertAtCursor(composeEl, text) {
  const body =
    composeEl.querySelector('[role="textbox"][g_editable="true"]') ||
    composeEl.querySelector('[role="textbox"]');
  if (!body) return;

  body.focus();

  // Move cursor to end of existing content
  const range = document.createRange();
  range.selectNodeContents(body);
  range.collapse(false);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);

  // Insert as plain text so Gmail doesn't apply weird formatting
  document.execCommand("insertText", false, "\n\n" + text);
}

function createButton() {
  const btn = document.createElement("div");
  btn.className = "cal-suggest-btn";
  btn.setAttribute("role", "button");
  btn.title = "Suggest meeting times from your calendar";
  btn.textContent = "📅 Suggest Times";
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

function injectButton(composeEl) {
  if (composeEl.querySelector(".cal-suggest-btn")) return;

  // Gmail's compose toolbar has multiple selectors depending on version
  const toolbar =
    composeEl.querySelector('[role="toolbar"]') ||
    composeEl.querySelector(".btC") ||
    composeEl.querySelector(".aDh");
  if (!toolbar) return;

  const btn = createButton();

  btn.addEventListener("click", async () => {
    btn.textContent = "⏳ Checking...";
    btn.style.pointerEvents = "none";
    try {
      const slots = await fetchSlots();
      insertAtCursor(composeEl, formatSlotsText(slots));
      btn.textContent = "✅ Inserted";
    } catch (err) {
      btn.textContent = "❌ Error";
      console.error("[cal-suggest]", err);
    } finally {
      setTimeout(() => {
        btn.textContent = "📅 Suggest Times";
        btn.style.pointerEvents = "auto";
      }, 2500);
    }
  });

  toolbar.appendChild(btn);
}

// Watch for compose windows being opened/closed
const observer = new MutationObserver(() => {
  document
    .querySelectorAll('[role="dialog"], .nH.Hd[aria-label]')
    .forEach((el) => {
      if (el.querySelector('[aria-label*="Subject"]')) {
        injectButton(el);
      }
    });
});

observer.observe(document.body, { childList: true, subtree: true });
