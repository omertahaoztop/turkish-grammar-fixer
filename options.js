"use strict";

const apiKeyInput = document.getElementById("api-key");
const toggleVisibilityBtn = document.getElementById("toggle-visibility");
const testApiBtn = document.getElementById("test-api");
const testResultDiv = document.getElementById("test-result");
const modelSelect = document.getElementById("model-select");
const saveBtn = document.getElementById("save-btn");
const saveStatus = document.getElementById("save-status");

async function loadModels() {
  modelSelect.innerHTML = '<option disabled>Modeller yukleniyor...</option>';
  try {
    const { models } = await browser.runtime.sendMessage({ type: "GET_MODELS" });
    const { selectedModel } = await browser.storage.local.get({ selectedModel: "" });
    modelSelect.innerHTML = "";
    models.forEach(({ id, name }) => {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = name;
      if (id === selectedModel) opt.selected = true;
      modelSelect.appendChild(opt);
    });
    if (!modelSelect.value && models.length) modelSelect.selectedIndex = 0;
  } catch {
    modelSelect.innerHTML = '<option value="google/gemini-2.0-flash-exp:free">Gemini 2.0 Flash (Google)</option>';
  }
}

async function init() {
  const { apiKey } = await browser.storage.local.get({ apiKey: "" });
  apiKeyInput.value = apiKey;
  await loadModels();
}

init();

toggleVisibilityBtn.addEventListener("click", () => {
  if (apiKeyInput.type === "password") {
    apiKeyInput.type = "text";
    toggleVisibilityBtn.textContent = "🙈";
  } else {
    apiKeyInput.type = "password";
    toggleVisibilityBtn.textContent = "👁";
  }
});

testApiBtn.addEventListener("click", async () => {
  const key = apiKeyInput.value.trim();
  if (!key) {
    showTestResult("error", "Lütfen önce API anahtarını girin.");
    return;
  }

  testApiBtn.disabled = true;
  showTestResult("loading", "Test ediliyor...");

  try {
    const response = await browser.runtime.sendMessage({
      type: "TEST_API_KEY",
      apiKey: key
    });

    if (response.success) {
      showTestResult("success", "✅ Bağlantı başarılı! API anahtarı çalışıyor.");
    } else {
      showTestResult("error", `❌ Hata: ${response.error}`);
    }
  } catch (err) {
    showTestResult("error", `❌ Beklenmeyen hata: ${err.message}`);
  } finally {
    testApiBtn.disabled = false;
  }
});

saveBtn.addEventListener("click", async () => {
  const apiKey = apiKeyInput.value.trim();
  const selectedModel = modelSelect.value;

  await browser.storage.local.set({ apiKey, selectedModel });

  saveStatus.classList.remove("hidden");
  setTimeout(() => saveStatus.classList.add("hidden"), 2500);
});

const tdkStatusEl = document.getElementById("tdk-status");
const refreshTdkBtn = document.getElementById("refresh-tdk");

async function updateTDKStatus() {
  const { tdkRules, tdkRulesCachedAt } = await browser.storage.local.get({ tdkRules: null, tdkRulesCachedAt: 0 });
  if (tdkRules) {
    const date = new Date(tdkRulesCachedAt).toLocaleDateString("tr-TR");
    const sections = (tdkRules.match(/^## /gm) || []).length;
    tdkStatusEl.textContent = `✅ ${sections} kural yüklendi (${date})`;
    tdkStatusEl.className = "tdk-status ok";
    return true;
  } else {
    tdkStatusEl.textContent = "TDK.gov.tr'den kurallar çekiliyor...";
    tdkStatusEl.className = "tdk-status loading";
    return false;
  }
}

async function pollUntilLoaded() {
  const done = await updateTDKStatus();
  if (!done) {
    setTimeout(pollUntilLoaded, 2000);
  }
}
refreshTdkBtn.addEventListener("click", async () => {
  refreshTdkBtn.disabled = true;
  tdkStatusEl.textContent = "Kurallar TDK'dan çekiliyor...";
  tdkStatusEl.className = "tdk-status loading";
  await browser.runtime.sendMessage({ type: "REFRESH_TDK_RULES" });
  setTimeout(async () => {
    await pollUntilLoaded();
    refreshTdkBtn.disabled = false;
  }, 1000);
});

pollUntilLoaded();

function showTestResult(type, message) {
  testResultDiv.className = `test-result ${type}`;
  testResultDiv.textContent = message;
  testResultDiv.classList.remove("hidden");
}
