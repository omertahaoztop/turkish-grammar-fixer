"""Kaynak metinle düzeltilmiş metin arasındaki farkı, kaynaktaki gerçek konumlara bağlı düzenlemelere çevirir."""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

_TOKEN = re.compile(r"\w+|\s+|[^\w\s]")


@dataclass
class Edit:
    start: int
    end: int
    original: str
    replacement: str
    sources: list[str] = field(default_factory=list)
    rule: str = ""
    explanation: str = ""
    confidence: float = 0.0

    @property
    def key(self) -> tuple[int, int, str]:
        return (self.start, self.end, self.replacement)


def _char_opcodes(src: str, tgt: str):
    a, b = _TOKEN.findall(src), _TOKEN.findall(tgt)
    ao, bo = [0], [0]
    for t in a:
        ao.append(ao[-1] + len(t))
    for t in b:
        bo.append(bo[-1] + len(t))
    sm = SequenceMatcher(None, a, b, autojunk=False)
    return [(tag, ao[i1], ao[i2], bo[j1], bo[j2]) for tag, i1, i2, j1, j2 in sm.get_opcodes()]


def _map(ops, p: int, end: bool) -> int:
    # Sınır bir eklemeye değebilir: bitiş eklemeyi kapsamalı, başlangıç atlamamalı.
    cands = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal" and i1 <= p <= i2:
            cands.append(j1 + p - i1)
        elif tag != "equal" and p in (i1, i2):
            cands += [j1, j2] if i1 == i2 else [j1 if p == i1 else j2]
    return max(cands) if end else min(cands)


def diff_edits(src: str, tgt: str) -> list[Edit]:
    """Değişen her bölgeyi kelime sınırlarına genişletir, örtüşenleri birleştirir."""
    if src == tgt:
        return []
    ops = _char_opcodes(src, tgt)
    spans: list[list[int]] = []
    for tag, i1, i2, _, _ in ops:
        if tag == "equal":
            continue
        a, b = i1, i2
        while a > 0 and not src[a - 1].isspace():
            a -= 1
        while b < len(src) and not src[b].isspace():
            b += 1
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    out = []
    for a, b in spans:
        c, d = _map(ops, a, False), _map(ops, b, True)
        if src[a:b] != tgt[c:d]:
            out.append(Edit(a, b, src[a:b], tgt[c:d]))
    return out


def apply_edits(src: str, edits: list[Edit]) -> str:
    out, pos = [], 0
    for e in sorted(edits, key=lambda e: e.start):
        if e.start < pos:
            continue
        out.append(src[pos:e.start])
        out.append(e.replacement)
        pos = e.end
    out.append(src[pos:])
    return "".join(out)


if __name__ == "__main__":
    cases = [
        ("Bende geldim ama sen gelmedin mi?", "Ben de geldim ama sen gelmedin mi?", [("Bende", "Ben de")]),
        ("Hiç bir zaman Ankaraya gitmedim.", "Hiçbir zaman Ankara'ya gitmedim.", [("Hiç bir", "Hiçbir"), ("Ankaraya", "Ankara'ya")]),
        ("Selam , nasılsın ?", "Selam, nasılsın?", [("Selam ,", "Selam,"), ("nasılsın ?", "nasılsın?")]),
        ("Bunu nasıl yaptın", "Bunu nasıl yaptın?", [("yaptın", "yaptın?")]),
        ("Sonuç olarak  her şey.", "Sonuç olarak her şey.", [("olarak  her", "olarak her")]),
        ("Aynı metin.", "Aynı metin.", []),
    ]
    for src, tgt, want in cases:
        got = diff_edits(src, tgt)
        assert [(e.original, e.replacement) for e in got] == want, (src, got)
        assert apply_edits(src, got) == tgt, (src, apply_edits(src, got))
    print("ok")
