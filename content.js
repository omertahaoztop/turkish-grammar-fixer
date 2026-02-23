"use strict";

let activeTooltip = null;
let loadingIndicator = null;
let lastRightClickTarget = null;

document.addEventListener("contextmenu", (e) => {
  lastRightClickTarget = e.target;
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    removeTooltip();
  }
});

document.addEventListener("click", (e) => {
  if (activeTooltip && !activeTooltip.contains(e.target)) {
    removeTooltip();
  }
});

browser.runtime.onMessage.addListener((message) => {
  if (message.type === "LOADING_START") {
    showLoadingIndicator();
  }

  if (message.type === "SHOW_CORRECTION") {
    removeLoadingIndicator();
    showCorrectionTooltip(message.result, message.originalText, message.mode);
  }

  if (message.type === "SHOW_ERROR") {
    removeLoadingIndicator();
    showErrorTooltip(message.message);
  }

  if (message.type === "GET_FIELD_TEXT") {
    const target = lastRightClickTarget;
    if (!target) return;

    const text = getEditableText(target);
    if (!text || text.trim().length === 0) {
      showErrorTooltip("Bu alanda düzenlenebilir metin bulunamadı.");
      return;
    }

    showLoadingIndicator();

    browser.runtime.sendMessage({
      type: "FIX_FIELD_TEXT",
      text: text
    }).then((response) => {
      removeLoadingIndicator();
      if (response.type === "ERROR") {
        showErrorTooltip(response.message);
      } else {
        showCorrectionTooltip(response.result, text, "field", target);
      }
    });
  }
});

function getEditableText(element) {
  if (element.isContentEditable) {
    return element.innerText;
  }
  if (element.tagName === "INPUT" || element.tagName === "TEXTAREA") {
    return element.value;
  }
  const editableParent = element.closest('[contenteditable="true"]');
  if (editableParent) return editableParent.innerText;

  return null;
}

function applyCorrection(element, correctedText) {
  if (!element) return;

  if (element.isContentEditable || element.closest('[contenteditable="true"]')) {
    const target = element.isContentEditable ? element : element.closest('[contenteditable="true"]');
    target.innerText = correctedText;
    const range = document.createRange();
    range.selectNodeContents(target);
    range.collapse(false);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  } else if (element.tagName === "INPUT" || element.tagName === "TEXTAREA") {
    element.value = correctedText;
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }
}

function showLoadingIndicator() {
  removeLoadingIndicator();

  loadingIndicator = document.createElement("div");
  loadingIndicator.className = "tyd-loading";
  loadingIndicator.innerHTML = `
    <div class="tyd-loading-inner">
      <div class="tyd-spinner"></div>
      <span>Yazım kontrol ediliyor...</span>
    </div>
  `;
  document.body.appendChild(loadingIndicator);
}

function removeLoadingIndicator() {
  if (loadingIndicator) {
    loadingIndicator.remove();
    loadingIndicator = null;
  }
}

function removeTooltip() {
  if (activeTooltip) {
    activeTooltip.remove();
    activeTooltip = null;
  }
}

function showErrorTooltip(message) {
  removeTooltip();

  const tooltip = buildTooltipShell("tyd-tooltip tyd-error");
  tooltip.innerHTML = `
    <div class="tyd-header">
      <span class="tyd-icon">⚠️</span>
      <strong>Hata</strong>
      <button class="tyd-close" title="Kapat">✕</button>
    </div>
    <div class="tyd-body">
      <p class="tyd-error-msg">${escapeHtml(message)}</p>
    </div>
  `;

  document.body.appendChild(tooltip);
  activeTooltip = tooltip;
  positionTooltip(tooltip);

  tooltip.querySelector(".tyd-close").addEventListener("click", removeTooltip);
}

function showCorrectionTooltip(result, originalText, mode, fieldElement = null) {
  removeTooltip();

  const hasErrors = result.hatalar && result.hatalar.length > 0;
  const tooltipClass = `tyd-tooltip ${hasErrors ? "tyd-has-errors" : "tyd-no-errors"}`;
  const tooltip = buildTooltipShell(tooltipClass);

  const modelBadge = result.usedModel
    ? `<span class="tyd-model-badge">${result.usedModel.split("/").pop().replace(":free", "")}</span>`
    : "";

  let errorsHtml = "";
  if (hasErrors) {
    errorsHtml = `
      <div class="tyd-errors-list">
        ${result.hatalar.map((hata, i) => `
          <div class="tyd-error-item">
            <div class="tyd-error-diff">
              <span class="tyd-wrong">${escapeHtml(hata.orijinal)}</span>
              <span class="tyd-arrow">→</span>
              <span class="tyd-correct">${escapeHtml(hata.duzeltilmis)}</span>
            </div>
            <div class="tyd-error-rule">${escapeHtml(hata.aciklama)}</div>
            ${hata.kural ? `<div class="tyd-tdk-rule">📖 ${escapeHtml(hata.kural)}</div>` : ""}
          </div>
        `).join("")}
      </div>
    `;
  }

  const correctedTextHtml = hasErrors ? `
    <div class="tyd-corrected-block">
      <div class="tyd-corrected-label">Düzeltilmiş metin:</div>
      <div class="tyd-corrected-text">${escapeHtml(result.tam_duzeltilmis_metin)}</div>
    </div>
  ` : "";

  const actionButtons = hasErrors ? `
    <div class="tyd-actions">
      ${(mode === "field" && fieldElement) ? `<button class="tyd-btn tyd-btn-apply" data-action="apply">✅ Uygula</button>` : ""}
      ${mode === "selection" ? `<button class="tyd-btn tyd-btn-copy" data-action="copy">📋 Kopyala</button>` : ""}
      <button class="tyd-btn tyd-btn-cancel" data-action="cancel">İptal</button>
    </div>
  ` : `
    <div class="tyd-actions">
      <button class="tyd-btn tyd-btn-cancel" data-action="cancel">Kapat</button>
    </div>
  `;

  tooltip.innerHTML = `
    <div class="tyd-header">
      <span class="tyd-icon">${hasErrors ? "✏️" : "✅"}</span>
      <strong>${hasErrors ? `${result.hatalar.length} hata bulundu` : "Yazım doğru!"}</strong>
      ${modelBadge}
      <button class="tyd-close" title="Kapat">✕</button>
    </div>
    <div class="tyd-body">
      <p class="tyd-ozet">${escapeHtml(result.ozet)}</p>
      ${errorsHtml}
      ${correctedTextHtml}
    </div>
    ${actionButtons}
  `;

  document.body.appendChild(tooltip);
  activeTooltip = tooltip;
  positionTooltip(tooltip);

  tooltip.querySelector(".tyd-close").addEventListener("click", removeTooltip);

  const applyBtn = tooltip.querySelector("[data-action='apply']");
  if (applyBtn) {
    applyBtn.addEventListener("click", () => {
      applyCorrection(fieldElement, result.tam_duzeltilmis_metin);
      removeTooltip();
    });
  }

  const copyBtn = tooltip.querySelector("[data-action='copy']");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      navigator.clipboard.writeText(result.tam_duzeltilmis_metin).then(() => {
        copyBtn.textContent = "✅ Kopyalandı!";
        setTimeout(removeTooltip, 1200);
      });
    });
  }

  const cancelBtn = tooltip.querySelector("[data-action='cancel']");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", removeTooltip);
  }
}

function buildTooltipShell(className) {
  const el = document.createElement("div");
  el.className = className;
  el.setAttribute("role", "dialog");
  el.setAttribute("aria-modal", "false");
  return el;
}

function positionTooltip(tooltip) {
  const selection = window.getSelection();
  let x, y;

  if (selection && selection.rangeCount > 0 && selection.toString().trim()) {
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    x = rect.left + window.scrollX;
    y = rect.bottom + window.scrollY + 8;
  } else if (lastRightClickTarget) {
    const rect = lastRightClickTarget.getBoundingClientRect();
    x = rect.left + window.scrollX;
    y = rect.bottom + window.scrollY + 8;
  } else {
    x = window.scrollX + 24;
    y = window.scrollY + 80;
  }

  tooltip.style.left = `${x}px`;
  tooltip.style.top = `${y}px`;

  requestAnimationFrame(() => {
    const tRect = tooltip.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    if (tRect.right > vw - 16) {
      tooltip.style.left = `${Math.max(8, vw - tRect.width - 16 + window.scrollX)}px`;
    }
    if (tRect.bottom > vh - 16) {
      const newTop = (y - window.scrollY) - tRect.height - 8;
      tooltip.style.top = `${newTop + window.scrollY}px`;
    }
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
