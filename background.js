const OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions";
const OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models";
const TDK_RULES_URLS = [
  "https://tdk.gov.tr/kategori/icerik/yazim-kurallari/",
  "https://tdk.gov.tr/kategori/icerik/yazim-kurallari/page/2/",
  "https://tdk.gov.tr/kategori/icerik/yazim-kurallari/page/3/",
  "https://tdk.gov.tr/kategori/icerik/yazim-kurallari/page/4/"
];

const SKIP_RULE_TITLES = new Set([
  "SUNUŞ", "Ses, Harf ve Alfabe", "Kısaltmalar Dizini",
  "Simgeler", "Ünlülerin Nitelikleri", "Ünsüzlerin Nitelikleri"
]);

const FALLBACK_MODELS = [
  "meta-llama/llama-3.3-70b-instruct:free",
  "openai/gpt-oss-120b:free",
  "mistralai/mistral-small-3.1-24b-instruct:free",
  "google/gemma-3-27b-it:free"
];

const MODELS_CACHE_TTL = 60 * 60 * 1000;
const RULES_CACHE_TTL = 7 * 24 * 60 * 60 * 1000;

let cachedFreeModels = null;
let modelsCacheTs = 0;

const PROMPT_SUFFIX = `

YAZIM KONTROLÜ YAPILIRKEN KESİNLİKLE UYULACAK KURALLAR:
- Konuşma dili sözcüklerini (dimi, hani, yani, işte, mesela, tamam, vs.) düzeltme — bunlar yazım hatası değil
- Kısaltmaları, argo ifadeleri, bölgesel söyleyişleri hedefle değil yazım olarak değerlendir
- "sen de" (bağlaç, ayrı) ≠ "sende" (bulunma hali, bitişik) — anlamı dikkate al
- "da/de" bağlacı her zaman ayrı; "da/de/ta/te" bulunma eki her zaman bitişik
- Unvan/saygı sözleri (Hocam, Bey, Hanım, Efendi vb.) hitap olarak kullanılıyorsa büyük harfle başlar: "Vedat Hocam, nasılsınız?" / "Merhaba Murat Bey" — cümle içinde sıradan isim tamlamasıysa küçük harfle yazılır: "Vedat hocam derste anlattı." / "Murat beyle konuştum."
- Teknik terimlerin kendine özgü büyük/küçük harf yazımını koru ve düzelt (örn: IPsec, GitLab, iPhone, JavaScript, TypeScript, macOS, iOS, WhatsApp, YouTube, LinkedIn, Wi-Fi, API, HTTP, SQL, Linux, GitHub, Docker, OpenAI)
- Şüphe durumunda düzeltme yapma; yanlış düzeltme hiç düzeltmemekten kötüdür

ÇIKTI FORMATI — Sadece bu JSON'ı döndür, başka hiçbir şey ekleme:
{
  "hatalar": [
    {
      "orijinal": "hatalı metin parçası",
      "duzeltilmis": "düzeltilmiş hali",
      "aciklama": "kısa kural açıklaması",
      "kural": "ilgili TDK kuralı"
    }
  ],
  "tam_duzeltilmis_metin": "tüm metnin düzeltilmiş hali",
  "ozet": "kaç hata bulundu ve genel değerlendirme"
}

Metin doğruysa: { "hatalar": [], "tam_duzeltilmis_metin": "<orijinal metin>", "ozet": "Metin TDK kurallarına göre doğru yazılmış." }`;

async function fetchFreeModels() {
  const now = Date.now();
  if (cachedFreeModels && now - modelsCacheTs < MODELS_CACHE_TTL) {
    return cachedFreeModels;
  }
  try {
    const response = await fetch(OPENROUTER_MODELS_URL);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    const free = data.data
      .filter(m => m.pricing?.prompt === "0" && m.id !== "openrouter/free")
      .map(m => ({ id: m.id, name: m.name }));
    cachedFreeModels = free;
    modelsCacheTs = now;
    return free;
  } catch {
    return FALLBACK_MODELS.map(id => ({ id, name: id }));
  }
}

async function fetchTDKRules() {
  const { tdkRules, tdkRulesCachedAt } = await browser.storage.local.get({
    tdkRules: null,
    tdkRulesCachedAt: 0
  });

  if (tdkRules && Date.now() - tdkRulesCachedAt < RULES_CACHE_TTL) {
    return tdkRules;
  }

  try {
    const articleUrls = await collectArticleUrls();
    const rules = await fetchAllArticles(articleUrls);
    const compiled = rules.join("\n\n");
    await browser.storage.local.set({ tdkRules: compiled, tdkRulesCachedAt: Date.now() });
    return compiled;
  } catch {
    return null;
  }
}

async function collectArticleUrls() {
  const pages = await Promise.all(TDK_RULES_URLS.map(async (pageUrl) => {
    try {
      const res = await fetch(pageUrl);
      const html = await res.text();
      return [...html.matchAll(/href='(https:\/\/tdk\.gov\.tr\/icerik\/yazim-kurallari\/[^']+)'/g)].map(m => m[1]);
    } catch {
      return [];
    }
  }));
  const seen = new Set();
  return pages.flat().filter(url => seen.has(url) ? false : seen.add(url));
}

async function fetchAllArticles(urls) {
  const fetched = await Promise.all(urls.map(async (url) => {
    try {
      const res = await fetch(url);
      const html = await res.text();
      const title = extractTitle(html);
      if (SKIP_RULE_TITLES.has(title)) return null;
      const content = extractArticleContent(html);
      return content.length > 50 ? `## ${title}\n${content}` : null;
    } catch {
      return null;
    }
  }));
  return fetched.filter(Boolean);
}

function extractTitle(html) {
  const m = html.match(/<h1[^>]*>(.*?)<\/h1>/s);
  if (!m) return "";
  return m[1].replace(/<[^>]+>/g, "").replace(/&#\d+;/g, c => String.fromCharCode(parseInt(c.slice(2)))).trim();
}

function extractArticleContent(html) {
  const m = html.match(/<article[^>]*>(.*?)<\/article>/s);
  if (!m) return "";
  let content = m[1];
  content = content.replace(/<script[^>]*>.*?<\/script>/gs, "");
  content = content.replace(/<style[^>]*>.*?<\/style>/gs, "");
  content = content.replace(/<br\s*\/?>/gi, "\n");
  content = content.replace(/<\/p>/gi, "\n");
  content = content.replace(/<\/li>/gi, "\n");
  content = content.replace(/<[^>]+>/g, "");
  content = content.replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n)));
  content = content.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&nbsp;/g, " ");
  content = content.replace(/[ \t]+/g, " ");
  content = content.replace(/\n{3,}/g, "\n\n");
  // Strip metadata lines (dates, category paths)
  content = content.split("\n").filter(l => {
    const t = l.trim();
    return t && !t.match(/^\d{1,2}\s+\w+\s+\d{4}/) && !t.startsWith("/Kategori") && !t.includes("tdk.gov.tr");
  }).join("\n");
  return content.trim();
}

function buildSystemPrompt(tdkRules) {
  const rulesSection = tdkRules
    ? `\nAşağıda TDK Yazım Kılavuzu'nun tüm yazım kuralları verilmiştir. Bu kurallara göre değerlendirme yap:\n\n${tdkRules}\n`
    : `\nTDK Yazım Kılavuzu kurallarını uygula.\n`;

  return `Sen bir Türkçe yazım ve dil uzmanısın. Türk Dil Kurumu (TDK) yazım kılavuzu ve İmlâ Kılavuzu'na göre metinleri düzeltiyorsun.${rulesSection}${PROMPT_SUFFIX}`;
}

browser.runtime.onInstalled.addListener(() => {
  browser.contextMenus.create({
    id: "fix-turkish-text",
    title: "Türkçe yazımı düzelt",
    contexts: ["selection", "editable"],
    icons: { "16": "icons/icon16.png", "32": "icons/icon48.png" }
  });
  browser.contextMenus.create({
    id: "fix-turkish-field",
    title: "Bu alanın tamamını düzelt",
    contexts: ["editable"]
  });
  });
  fetchTDKRules();

browser.contextMenus.onClicked.addListener(async (info, tab) => {
  const apiKey = await getApiKey();
  if (!apiKey) {
    browser.tabs.sendMessage(tab.id, {
      type: "SHOW_ERROR",
      message: "OpenRouter API anahtarı bulunamadı. Lütfen eklenti ayarlarından API anahtarınızı girin."
    });
    return;
  }

  if (info.menuItemId === "fix-turkish-text") {
    const text = info.selectionText;
    if (!text || text.trim().length === 0) return;
    browser.tabs.sendMessage(tab.id, { type: "LOADING_START", text });
    try {
      const result = await checkGrammar(text, apiKey);
      browser.tabs.sendMessage(tab.id, { type: "SHOW_CORRECTION", result, originalText: text, mode: "selection" });
    } catch (error) {
      browser.tabs.sendMessage(tab.id, { type: "SHOW_ERROR", message: `Hata oluştu: ${error.message}` });
    }
  }

  if (info.menuItemId === "fix-turkish-field") {
    browser.tabs.sendMessage(tab.id, { type: "GET_FIELD_TEXT" });
  }
});

browser.runtime.onMessage.addListener(async (message, sender) => {
  if (message.type === "FIX_FIELD_TEXT") {
    const apiKey = await getApiKey();
    if (!apiKey) return { type: "ERROR", message: "API anahtarı bulunamadı." };
    try {
      const result = await checkGrammar(message.text, apiKey);
      return { type: "CORRECTION_RESULT", result };
    } catch (error) {
      return { type: "ERROR", message: error.message };
    }
  }

  if (message.type === "GET_MODELS") {
    const models = await fetchFreeModels();
    return { models };
  }

  if (message.type === "REFRESH_TDK_RULES") {
    await browser.storage.local.remove(["tdkRules", "tdkRulesCachedAt"]);
    fetchTDKRules();
    return { success: true };
  }

  if (message.type === "TEST_API_KEY") {
    try {
      await checkGrammar("Merhaba, bu bir test metnidir.", message.apiKey);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
});

async function checkGrammar(text, apiKey) {
  const [freeModels, tdkRules] = await Promise.all([
    fetchFreeModels(),
    fetchTDKRules()
  ]);
  const defaultModel = freeModels[0]?.id || FALLBACK_MODELS[0];
  const { selectedModel } = await browser.storage.local.get({ selectedModel: defaultModel });

  const systemPrompt = buildSystemPrompt(tdkRules);
  const requestBody = {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: `Şu metni TDK yazım kurallarına göre incele ve düzelt:\n\n"${text}"` }
    ],
    temperature: 0.1,
    max_tokens: 2048,
    response_format: { type: "json_object" }
  };

  let lastError = null;
  const modelsToTry = [selectedModel, ...freeModels.map(m => m.id).filter(id => id !== selectedModel)];

  for (const model of modelsToTry) {
    try {
      const response = await fetch(OPENROUTER_API_URL, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${apiKey}`,
          "Content-Type": "application/json",
          "HTTP-Referer": "https://github.com/turkish-grammar-fixer",
          "X-Title": "Turkce Yazim Duzeltici"
        },
        body: JSON.stringify({ ...requestBody, model })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData?.error?.message || `HTTP ${response.status}`;
        // Rate limit veya gecici hata ise sonraki modeli dene
        if (response.status === 429 || response.status === 503 || response.status === 502) {
          lastError = new Error(`${model}: ${errorMsg}`);
          continue;
        }
        throw new Error(errorMsg);
      }

      const data = await response.json();
      const content = data.choices?.[0]?.message?.content;
      if (!content) throw new Error("API bos yanit dondurdu.");

      let parsed;
      try {
        parsed = JSON.parse(content);
      } catch {
        parsed = { hatalar: [], tam_duzeltilmis_metin: content, ozet: "Ham yanit" };
      }
      return { ...parsed, usedModel: model };

    } catch (error) {
      if (error.message.includes("API bos") || error.message.includes("HTTP 4")) throw error;
      lastError = error;
      continue;
    }
  }

  throw lastError || new Error("Tum modeller basarisiz oldu.");
}

async function getApiKey() {
  const { apiKey } = await browser.storage.local.get({ apiKey: "" });
  return apiKey.trim() || null;
}
