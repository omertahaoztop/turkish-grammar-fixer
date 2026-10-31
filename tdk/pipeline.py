"""Kaynakları çalıştırır, önerileri birleştirir ve güven puanı verir."""

import re
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from math import prod

from .edits import Edit
from .engines import LLMEngine, RuleEngine, tr_lower

CHUNK = 600


def chunks(text: str) -> list[tuple[int, str]]:
    """Metni paragraf ve cümle sınırlarından, her parça en fazla CHUNK karakter olacak biçimde böler."""
    out = []
    for m in re.finditer(r"[^\n]*\n?", text):
        para = m.group()
        if not para:
            continue
        if len(para) <= CHUNK:
            out.append((m.start(), para))
            continue
        buf_start, buf = m.start(), ""
        for s in re.finditer(r".*?(?:[.!?…]+\s+|$)", para, re.DOTALL):
            if buf and len(buf) + len(s.group()) > CHUNK:
                out.append((buf_start, buf))
                buf_start, buf = m.start() + s.start(), ""
            buf += s.group()
        if buf:
            out.append((buf_start, buf))
    return [(o, c) for o, c in out if c.strip()]


def _plausible(e: Edit) -> bool:
    """Tek bir öneri anlam değiştiren yeniden yazım gibi duruyorsa elenir."""
    a, b = tr_lower(e.original), tr_lower(e.replacement)
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.6 or len(a) <= 4


def merge(cands: list[Edit]) -> list[Edit]:
    cands = sorted((e for e in cands if _plausible(e)), key=lambda e: (e.start, e.end))
    groups: list[list[Edit]] = []
    for e in cands:
        if groups and e.start < max(g.end for g in groups[-1]):
            groups[-1].append(e)
        else:
            groups.append([e])
    out = []
    for g in groups:
        # Farklı sınırlarla aynı sonucu veren öneriler, grubun ortak aralığındaki sonuca göre oylanır.
        lo, hi = min(e.start for e in g), max(e.end for e in g)
        votes: dict[str, list[Edit]] = {}
        for e in g:
            votes.setdefault(tr_lower(_span_after(e, lo, hi, g)), []).append(e)
        best = max(votes.values(), key=lambda es: 1 - prod(1 - e.confidence for e in es))
        # Aynı düzeltmeyi öneren kaynaklar arasında büyük harf düzeni modelden alınır.
        pick = next((e for e in best if e.rule == "model"), best[0])
        out.append(Edit(pick.start, pick.end, pick.original, pick.replacement,
                        sorted({s for e in best for s in e.sources}),
                        next((e.rule for e in best if e.rule != "model"), "model"),
                        next((e.explanation for e in best if e.explanation), ""),
                        round(1 - prod(1 - e.confidence for e in best), 3)))
    return out


def _span_after(e: Edit, lo: int, hi: int, g: list[Edit]) -> str:
    text = {}
    for x in g:
        for i, ch in enumerate(x.original):
            text[x.start + i] = ch
    before = "".join(text.get(i, "\0") for i in range(lo, e.start))
    after = "".join(text.get(i, "\0") for i in range(e.end, hi))
    return before + e.replacement + after


class Pipeline:
    def __init__(self, rules: RuleEngine | None, llm: LLMEngine | None = None, cloud: LLMEngine | None = None):
        self.rules, self.llm, self.cloud = rules, llm, cloud
        self.errors: list[str] = []

    def check(self, text: str, use_cloud: bool = False, examples=(), fast: bool = False,
              errors: list[str] | None = None) -> list[Edit]:
        # Eşzamanlı istekler birbirinin hatasını görmesin diye çağıran kendi listesini verebilir.
        errors = self.errors if errors is None else errors
        cands = self.rules.check(text) if self.rules else []
        engines = [] if fast else [e for e in (self.llm, self.cloud if use_cloud else None) if e]
        if engines:
            jobs = [(eng, off, part) for eng in engines for off, part in chunks(text)]
            with ThreadPoolExecutor(4) as ex:
                for off, edits in ex.map(lambda j: (j[1], self._safe(j[0], j[2], examples, errors)), jobs):
                    for e in edits:
                        e.start += off
                        e.end += off
                        cands.append(e)
        return merge(cands)

    def _safe(self, engine: LLMEngine, text: str, examples, errors: list[str]) -> list[Edit]:
        # Model erişilemezse kalan kaynaklarla devam edilir; hata günlüğe yazılır.
        try:
            return engine.check(text, examples)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{engine.name}: {e}")
            return []
