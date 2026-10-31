"""Düzeltme kaynakları: kural motoru (akana + sözlük) ve OpenAI uyumlu LLM (llama-server veya OpenRouter)."""

import json
import re
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

import akana

from .edits import Edit, diff_edits

LEXICON = Path(__file__).parent / "data" / "lexicon.tsv"


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def tr_upper_first(s: str) -> str:
    return (s[0].replace("i", "İ").replace("ı", "I").upper() + s[1:]) if s else s


def match_case(orig: str, repl: str) -> str:
    """Kaynağın büyük harf düzenini korur: akana'nın 'Bende -> Ben De' hatasını da düzeltir."""
    if orig.isupper() and len(orig) > 1:
        return repl.upper()
    if orig[:1].isupper() and orig[1:] == tr_lower(orig[1:]):
        return tr_upper_first(tr_lower(repl))
    if orig == tr_lower(orig):
        return tr_lower(repl)
    return repl


def load_lexicon(*paths: Path) -> list[tuple[re.Pattern, str]]:
    entries = []
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            wrong, right = line.split("\t", 1)
            stem = wrong.endswith("*")
            wrong = tr_lower(wrong.rstrip("*"))
            pat = rf"(?<!\w){re.escape(wrong)}" + (r"(\w*)" if stem else "") + r"(?!\w)"
            entries.append((re.compile(pat), right.strip()))
    return entries


class RuleEngine:
    name = "kural"

    def __init__(self, extra_lexicons: tuple[Path, ...] = ()):
        self.extra = extra_lexicons
        self.reload()

    def reload(self):
        self.lexicon = load_lexicon(LEXICON, *self.extra)

    def check(self, text: str) -> list[Edit]:
        return self._lexicon(text) + self._akana(text)

    def _lexicon(self, text: str) -> list[Edit]:
        low, out = tr_lower(text), []
        for pat, right in self.lexicon:
            for m in pat.finditer(low):
                orig = text[m.start():m.end()]
                repl = match_case(orig, right + (m.group(1) if pat.groups else ""))
                if repl != orig:
                    out.append(Edit(m.start(), m.end(), orig, repl, ["sözlük"], "sözlük",
                                    "Sık yapılan yazım yanlışı.", 0.85))
        return out

    def _akana(self, text: str) -> list[Edit]:
        raw = text.encode()
        out = []
        for f in akana.check_grammar(text).findings:
            a = len(raw[:f.start_offset].decode(errors="ignore"))
            b = len(raw[:f.end_offset].decode(errors="ignore"))
            orig = text[a:b]
            repl = match_case(orig, f.replacement)
            if repl != orig:
                out.append(Edit(a, b, orig, repl, ["akana"], f.category, f.message_tr, f.confidence * 0.75))
        return out


SYSTEM_PROMPT = """Sen Türkçe yazım denetçisisin. Verilen metindeki yazım, noktalama, büyük/küçük harf, bitişik/ayrı yazım ve kesme işareti hatalarını TDK Yazım Kılavuzu'na göre düzelt.
Kurallar:
- Yalnız hataları düzelt; kelime seçimini, cümle yapısını ve üslubu değiştirme.
- Konuşma dilini, argoyu ve kısaltmaları olduğu gibi bırak.
- Yabancı teknik terimleri ve ürün adlarını (deploy, pipeline, PR, log) koru; ürün adının yerleşik yazımı farklıysa düzelt (gitlab -> GitLab).
- Bağlaç olan "de/da" ve "ki" ayrı, bulunma eki "-de/-da" ve "-ki" sıfat eki bitişik yazılır. Soru eki "mi" ayrı yazılır.
- Özel adlara gelen ekler kesme işaretiyle ayrılır; cins adlara kesme işareti konmaz.
- Emin değilsen dokunma.
- Yanıt olarak yalnız düzeltilmiş metni ver; açıklama, tırnak, başlık ekleme. Metin doğruysa aynen geri ver."""

FEW_SHOT = [
    ("Bende geldim, ankaraya gidiyoruz değilmi?", "Ben de geldim, Ankara'ya gidiyoruz değil mi?"),
    ("Kitap sende mi? Toplantı da konuştuk.", "Kitap sende mi? Toplantıda konuştuk."),
    ("Deploy ettim, pipeline'ı kontrol eder misin?", "Deploy ettim, pipeline'ı kontrol eder misin?"),
]

PII_NOTE = "\n- {{AD_1}} biçimindeki yer tutucular kişisel veridir; onları ve eklerini olduğu gibi bırak."


def _clean_output(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```\w*\n?|\n?```$", "", s).strip()
    if len(s) > 1 and s[0] == s[-1] and s[0] in "\"'“”":
        s = s[1:-1]
    return s


class LLMEngine:
    def __init__(self, name: str, base_url: str, model: str, api_key: str | None = None,
                 weight: float = 0.6, timeout: float = 120, extra: dict | None = None, mask_pii: bool = False):
        self.name, self.base_url, self.model, self.api_key = name, base_url.rstrip("/"), model, api_key
        self.weight, self.timeout, self.extra = weight, timeout, extra or {}
        self.pii = akana.TurkishPiiEngine() if mask_pii else None

    def correct(self, text: str, examples: list[tuple[str, str]] = ()) -> str:
        mapping = None
        if self.pii:
            masked = self.pii.mask(text)
            text, mapping = masked["masked_text"], masked["mapping"]
        messages = [{"role": "system", "content": SYSTEM_PROMPT + PII_NOTE * bool(mapping)}]
        # Kullanıcının geçmiş metinleri maskelenmeden buluta gitmesin diye öğrenilmiş örnekler yalnız yerelde kullanılır.
        for src, tgt in [*FEW_SHOT, *(() if self.pii else examples)]:
            messages += [{"role": "user", "content": src}, {"role": "assistant", "content": tgt}]
        messages.append({"role": "user", "content": text})
        body = {"model": self.model, "messages": messages, "temperature": 0,
                "max_tokens": 2 * len(text) + 512, **self.extra}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(f"{self.base_url}/chat/completions", json.dumps(body).encode(), headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            data = json.load(r)
        out = _clean_output(data["choices"][0]["message"]["content"] or "")
        return self.pii.restore(out, mapping) if mapping else out

    def check(self, text: str, examples: list[tuple[str, str]] = ()) -> list[Edit]:
        out = self.correct(text, examples)
        # Metni baştan yazan yanıt düzeltme değildir; tümüyle yok sayılır.
        if not out or SequenceMatcher(None, text, out, autojunk=False).ratio() < 0.8:
            return []
        edits = diff_edits(text, out)
        for e in edits:
            e.sources, e.rule, e.confidence = [self.name], "model", self.weight
        return edits
