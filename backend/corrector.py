import re
import zeyrek

_analyzer = zeyrek.MorphAnalyzer()

_BACK_VOWELS = set("aıouAIOU")
_ALL_VOWELS = _BACK_VOWELS | set("eiöüEİÖÜ")
_HARD_CONSONANTS = set("çfhkpsşt")

_TR_UPPER = str.maketrans(
    "abcçdefgğhıijklmnoöprsştuüvyz", "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"
)
_TR_LOWER = str.maketrans(
    "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ", "abcçdefgğhıijklmnoöprsştuüvyz"
)

_WORD_RE = re.compile(r"[^\s]+")
_SENTENCE_END = re.compile(r"([.!?]\s+)([a-züöıiçşğ])", re.UNICODE)
_DE_SUFFIX_RE = re.compile(r"^(.{2,})([dt][ae])$")
_MI_SUFFIX_RE = re.compile(
    r"^(.{2,})(m[ıiuü])((?:s[ıiuü]n?|y[ıiuü]z|n[ıiuü]z|sun|sün|sın|sin|lar|ler|ydı|yse|ken)?)$"
)

# TDK: Bağlaç da/de ASLA ta/te biçiminde yazılmaz.
# Kaynak: tdk.gov.tr/icerik/yazim-kurallari/baglac-olan-da-denin-yazilisi/
_CONJUNCTION_DA_DE = {"da", "de"}

# TDK: Bağlaç ki kalıplaşmış örneklerde bitişik yazılır.
# Kaynak: tdk.gov.tr/icerik/yazim-kurallari/baglac-olan-kinin-yazilisi/
_KI_MERGED_EXCEPTIONS = frozenset({
    "belki", "çünkü", "halbuki", "hâlbuki", "mademki",
    "meğerki", "oysaki", "sanki",
})

# TDK: Büyük ünlü uyumuna göre -la/-le eki (ile bağlacının bitişik biçimi)
# Kaynak: tdk.gov.tr/icerik/yazim-kurallari/ile-nin-yazilisi/
_ILE_SUFFIX_RE = re.compile(r"^(.{2,})(l[ae])$")

# TDK: a/e ile biten fiil + -yor → ünlü daralması (başlayor → başlıyor)
# Kaynak: tdk.gov.tr/icerik/yazim-kurallari/unlu-daralmasi/
# İstisna: deyince/deyip → e korunur (sadece -yor ekinden önce daralır)
_YOR_SUFFIX_RE = re.compile(
    r"^(.{2,}[ae])(yor(?:um|sun|uz|sunuz|lar|du|dun|duk|dunuz|dular|sa|san|sak|sanız|salar|ken)?)$"
)


def _tr_lower(s: str) -> str:
    return s.translate(_TR_LOWER)


def _last_vowel(word: str) -> str | None:
    for ch in reversed(_tr_lower(word)):
        if ch in _ALL_VOWELS:
            return ch
    return None


def _last_char(word: str) -> str:
    return _tr_lower(word[-1]) if word else ""


def _correct_de_suffix(stem: str) -> str:
    lv = _last_vowel(stem)
    lc = _last_char(stem)
    vowel = "a" if (lv and lv in _BACK_VOWELS) else "e"
    cons = "t" if lc in _HARD_CONSONANTS else "d"
    return cons + vowel


def _correct_mi_suffix(stem: str) -> str:
    lv = _last_vowel(stem)
    if lv in ("a", "ı"):
        return "mı"
    if lv in ("o", "u"):
        return "mu"
    if lv in ("ö", "ü"):
        return "mü"
    return "mi"


def _zeyrek_pos(word: str) -> str | None:
    results = _analyzer.analyze(word)
    if not results or not results[0]:
        return None
    first = results[0][0]
    pos = first.pos if hasattr(first, "pos") else None
    return None if pos == "Unk" else pos


def _zeyrek_has_loc(word: str) -> bool:
    results = _analyzer.analyze(word)
    if not results or not results[0]:
        return False
    return any(
        "Loc" in p.morphemes for p in results[0] if isinstance(p.morphemes, list)
    )


def _narrow_vowel_for_yor(stem_lower: str) -> str:
    """a/e ile biten fiil kökü + -yor öncesi daralması.
    TDK: başla-+yor → başlıyor, söyle-+yor → söylüyor, de-+yor → diyor.
    Küçük ünlü uyumu: önceki ünlü ö/ü ise ü, o/u ise u, yoksa a→ı / e→i.
    """
    _ALL_VOWELS_STR = "aeıioöuü"
    last_v = stem_lower[-1]  # regex garantisi: 'a' veya 'e'
    vowels = [ch for ch in stem_lower if ch in _ALL_VOWELS_STR]
    if last_v == "a":
        return "ı"
    # last_v == 'e': önceki ünlüe göre karar ver
    if len(vowels) >= 2:
        prev_v = vowels[-2]
        if prev_v in ("ö", "ü"):
            return "ü"
        if prev_v in ("o", "u"):
            return "u"
    return "i"


def correct(text: str) -> dict:
    changes: list[dict] = []
    tokens = list(_tokenize(text))
    result_tokens = list(tokens)

    for i, (raw, is_word, start) in enumerate(tokens):
        if not is_word:
            continue

        low = _tr_lower(raw)

        # ── Kural 1: Bağlaç da/de uyum hatası + ta/te biçimi ─────────────
        # TDK: Bağlaç ASLA ta/te biçiminde yazılmaz.
        # ta/te → doğrudan düzelt (Conj onayı bekleme).
        # da/de → yalnızca sesli uyumu yanlışsa düzelt.
        if low in ("da", "de", "ta", "te"):
            pos = _zeyrek_pos(raw)
            is_invalid_form = low in ("ta", "te")
            if pos == "Conj" or is_invalid_form:
                prev = _get_prev_word(result_tokens, i)
                if prev:
                    correct_conj = _correct_de_suffix(prev)
                    if low != correct_conj:
                        result_tokens[i] = (correct_conj, True, start)
                        if is_invalid_form:
                            hint = f'Bağlaç "ta/te" biçimi TDK\'ya göre hatalı: "{raw}" → "{correct_conj}"'
                            error_type = "conjunction_invalid_form"
                        else:
                            hint = f'Bağlaç uyumu: "{raw}" → "{correct_conj}"'
                            error_type = "conjunction_harmony"
                        changes.append(
                            {
                                "type": error_type,
                                "original": raw,
                                "fixed": correct_conj,
                                "hint": hint,
                            }
                        )
            continue

        # ── Kural 2: Bitişik hal eki uyum hatası ────────────────────────────
        # "masade" → "masada",  "evda" → "evde",  "kitapde" → "kitapta"
        # Zeyrek doğru yazılmış kelimede Loc döndürür → dokunma.
        # Yanlış yazılmış (Unk) → köke sor: isim/sıfat mı?
        de_m = _DE_SUFFIX_RE.match(low)
        if de_m:
            stem_low = de_m.group(1)
            suffix_low = de_m.group(2)
            stem_orig = raw[: len(stem_low)]

            if _zeyrek_has_loc(raw):
                continue

            stem_pos = _zeyrek_pos(stem_orig)
            if stem_pos in ("Noun", "Adj", "Pron", "Num"):
                correct_suffix = _correct_de_suffix(stem_low)
                if suffix_low != correct_suffix:
                    fixed = stem_orig + correct_suffix
                    result_tokens[i] = (fixed, True, start)
                    changes.append(
                        {
                            "type": "locative_harmony",
                            "original": raw,
                            "fixed": fixed,
                            "hint": f'Hal eki uyumu: "{raw}" → "{fixed}"',
                        }
                    )
            continue

        # ── Kural 3: Soru eki bitişik yazım + uyum ─────────────────────────
        # "geldimi" → "geldi mi",  "biliyor musun" zaten ayrı → doğru (bu regex yakalamaz)
        mi_m = _MI_SUFFIX_RE.match(low)
        if mi_m:
            stem_low = mi_m.group(1)
            mi_low = mi_m.group(2)
            rest_low = mi_m.group(3)
            stem_orig = raw[: len(stem_low)]

            stem_pos = _zeyrek_pos(stem_orig)
            if stem_pos in ("Verb", "Adj", "Adv", None):
                correct_mi = _correct_mi_suffix(stem_low)
                fixed = stem_orig + " " + correct_mi + rest_low
                if fixed != raw:
                    result_tokens[i] = (fixed, True, start)
                    changes.append(
                        {
                            "type": "question_particle",
                            "original": raw,
                            "fixed": fixed,
                            "hint": f'Soru eki ayrı yazılmalı: "{raw}" → "{fixed}"',
                        }
                    )

        # ── Kural 4: Bağlaç "ki" ayrı yazılmalı ──────────────────────────
        # TDK: Bağlaç ki ayrı yazılır. İstisnalar: belki, çünkü, halbuki vb.
        # Yakaladığımız hata: kelime sonuna yapışık "ki" → ayrı yaz.
        # _KI_MERGED_EXCEPTIONS listesindeki kalıplaşmış sözcüklere dokunma.
        # DİKKAT: "-ki" sıfat eki (masadaki, bugünkü) ile karışmaması için
        # tam kelime zeyrek'e Unknown ise ve kökü isim/zamir/zarf ise ayır.
        if low.endswith("ki") and len(low) > 2:
            if low not in _KI_MERGED_EXCEPTIONS:
                stem_candidate = raw[:-2]
                full_pos = _zeyrek_pos(raw)
                stem_pos_ki = _zeyrek_pos(stem_candidate)
                if full_pos is None and stem_pos_ki in ("Noun", "Pron", "Adv", "Verb"):
                    fixed = stem_candidate + " ki"
                    result_tokens[i] = (fixed, True, start)
                    changes.append(
                        {
                            "type": "conjunction_ki_merged",
                            "original": raw,
                            "fixed": fixed,
                            "hint": f'Bağlaç "ki" ayrı yazılmalı: "{raw}" → "{fixed}"',
                        }
                    )

        # ── Kural 5: Ünlü daralması — a/e ile biten fiil + -yor ──────────────
        # TDK: başla+yor → başlıyor, de+yor → diyor.
        # Yakaladığımız hata: kelime a/e ile bitiyor, ardından 'yor' var.
        # Zeyrek tam kelimeyi tanıyorsa (Verb) → dokunma (zaten doğru).
        # Tanımıyorsa (None) ve stem'i Verb olarak analiz ediyorsa → düzelt.
        yor_m = _YOR_SUFFIX_RE.match(low)
        if yor_m:
            stem_low = yor_m.group(1)          # a/e ile biten kök
            yor_part = yor_m.group(2)           # yor + ek
            stem_orig = raw[: len(stem_low)]
            # Tam kelime zeyrek tarafından tanınıyorsa → zaten doğru, atla
            if _zeyrek_pos(raw) is not None:
                pass
            else:
                stem_verb_pos = _zeyrek_pos(stem_orig)
                if stem_verb_pos == "Verb":
                    narrow = _narrow_vowel_for_yor(stem_low)
                    fixed = stem_orig[:-1] + narrow + yor_part
                    result_tokens[i] = (fixed, True, start)
                    changes.append(
                        {
                            "type": "vowel_narrowing",
                            "original": raw,
                            "fixed": fixed,
                            "hint": f'Ünlü daralması: "{raw}" → "{fixed}"',
                        }
                    )
            continue

        # ── Kural 7: -la/-le ekinin yanlış büyük ünlü uyumu ──────────────
        # TDK: kalın ünlülü kelime + -la, ince ünlülü + -le.
        # Hata: arkadaşle → arkadaşla, çiçekla → çiçekle.
        # Zeyrek doğru yazılmış kelimeyi tam analiz eder → dokunma.
        ile_m = _ILE_SUFFIX_RE.match(low)
        if ile_m:
            stem_low = ile_m.group(1)
            suffix_low = ile_m.group(2)         # 'la' veya 'le'
            stem_orig = raw[: len(stem_low)]
            # Tam kelime (ör. 'arkadaşla') zeyrek tanıyorsa doğru kabul et
            if _zeyrek_pos(raw) is not None:
                continue
            # Kök isim/zamir/sıfat mı?
            stem_pos_ile = _zeyrek_pos(stem_orig)
            if stem_pos_ile in ("Noun", "Pron", "Adj", "Num"):
                lv = _last_vowel(stem_low)
                correct_suffix = "la" if (lv and lv in _BACK_VOWELS) else "le"
                if suffix_low != correct_suffix:
                    fixed = stem_orig + correct_suffix
                    result_tokens[i] = (fixed, True, start)
                    changes.append(
                        {
                            "type": "ile_harmony",
                            "original": raw,
                            "fixed": fixed,
                            "hint": f'"-ile" eki uyumu: "{raw}" → "{fixed}"',
                        }
                    )

    corrected = _rebuild(result_tokens)
    corrected, cap_changes = _fix_capitalization(corrected)
    changes.extend(cap_changes)

    return {"corrected": corrected, "changes": changes}


def _tokenize(text: str):
    pos = 0
    for m in _WORD_RE.finditer(text):
        if m.start() > pos:
            yield (text[pos : m.start()], False, pos)
        yield (m.group(), True, m.start())
        pos = m.end()
    if pos < len(text):
        yield (text[pos:], False, pos)


def _rebuild(tokens) -> str:
    return "".join(raw for raw, _, _ in tokens)


def _get_prev_word(result_tokens, current_idx: int) -> str | None:
    for j in range(current_idx - 1, -1, -1):
        raw, is_word, _ = result_tokens[j]
        if is_word and raw.strip():
            return raw
    return None


def _fix_capitalization(text: str) -> tuple[str, list]:
    changes: list[dict] = []

    def replacer(m):
        punct, letter = m.group(1), m.group(2)
        up = letter.translate(_TR_UPPER)
        if up != letter:
            changes.append(
                {
                    "type": "capitalization",
                    "original": letter,
                    "fixed": up,
                    "hint": f'Cümle başı büyük harf: "{letter}" → "{up}"',
                }
            )
        return punct + up

    result = _SENTENCE_END.sub(replacer, text)

    stripped = result.lstrip()
    if stripped and stripped[0] in "abcçdefgğhıijklmnoöprsştuüvyz":
        up = stripped[0].translate(_TR_UPPER)
        leading = result[: len(result) - len(stripped)]
        result = leading + up + stripped[1:]
        changes.append(
            {
                "type": "capitalization",
                "original": stripped[0],
                "fixed": up,
                "hint": f'Metin başı büyük harf: "{stripped[0]}" → "{up}"',
            }
        )

    return result, changes
