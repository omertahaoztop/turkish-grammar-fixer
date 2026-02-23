"use strict";

const BACKEND_URL = "http://127.0.0.1:5858/correct";

browser.runtime.onMessage.addListener((msg) => {
  if (msg.type !== "FIX_SELECTION") return;
  fixActiveSelection();
});

function getActiveRange() {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
  return sel.getRangeAt(0);
}

async function fixActiveSelection() {
  const range = getActiveRange();
  if (!range) return;

  const originalText = range.toString();
  if (!originalText.trim()) return;

  showToast("Düzeltiliyor\u2026", "info");

  let result;
  try {
    const resp = await fetch(BACKEND_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: originalText }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    result = await resp.json();
  } catch (err) {
    showToast(
      `Backend'e ula\u015f\u0131lamad\u0131.<br><small>${escHtml(String(err))}</small><br>` +
        `<small><b>./start-backend.sh</b> komutunu \u00e7al\u0131\u015ft\u0131rd\u0131\u011f\u0131ndan emin ol.</small>`,
      "error"
    );
    return;
  }

  const { corrected, changes } = result;

  if (corrected === originalText) {
    showToast("Yaz\u0131m hatas\u0131 bulunamad\u0131.", "info");
    return;
  }

  const activeEl = document.activeElement;
  const isEditable =
    activeEl &&
    (activeEl.tagName === "TEXTAREA" ||
      activeEl.tagName === "INPUT" ||
      activeEl.isContentEditable);

  if (isEditable) {
    replaceInEditableElement(activeEl, originalText, corrected);
  } else {
    replaceViaRange(range, corrected);
  }

  showDiffToast(changes);
}

function replaceInEditableElement(el, originalText, corrected) {
  if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
    const start = el.selectionStart;
    const end = el.selectionEnd;
    el.value = el.value.slice(0, start) + corrected + el.value.slice(end);
    el.selectionStart = start;
    el.selectionEnd = start + corrected.length;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  } else {
    document.execCommand("insertText", false, corrected);
  }
}

function replaceViaRange(range, corrected) {
  range.deleteContents();
  range.insertNode(document.createTextNode(corrected));
}

function showDiffToast(changes) {
  if (!changes || changes.length === 0) return;

  const lines = changes
    .slice(0, 5)
    .map(
      (c) =>
        `<span class="tgf-orig">${escHtml(c.original)}</span> \u2192 ` +
        `<span class="tgf-fixed">${escHtml(c.fixed)}</span> ` +
        `<small>(${escHtml(c.hint)})</small>`
    )
    .join("<br>");

  const extra =
    changes.length > 5
      ? `<br><small>\u2026ve ${changes.length - 5} de\u011fi\u015fiklik daha</small>`
      : "";

  showToast(lines + extra, "success");
}

function showToast(html, type) {
  const existing = document.getElementById("tgf-toast");
  if (existing) existing.remove();

  const toast = document.createElement("div");
  toast.id = "tgf-toast";
  toast.className = `tgf-toast tgf-toast--${type}`;
  toast.innerHTML = html;
  document.body.appendChild(toast);

  requestAnimationFrame(() => toast.classList.add("tgf-toast--visible"));

  const timeout = type === "success" ? 5000 : type === "error" ? 6000 : 2500;
  setTimeout(() => {
    toast.classList.remove("tgf-toast--visible");
    setTimeout(() => toast.remove(), 300);
  }, timeout);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
