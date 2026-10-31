"""Değerlendirme: kendi altın set (düzenleme F0.5, temiz metinde yanlış alarm) ve GECTurk film yorumları (hata tespiti F0.5)."""

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tdk.config import build_pipeline
from tdk.edits import apply_edits, diff_edits

HERE = Path(__file__).parent


def f05(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 1.25 * p * r / (0.25 * p + r) if p + r else 0.0
    return round(p, 3), round(r, 3), round(f, 3)


def run(pipe, texts, threshold, use_cloud, workers):
    def one(src):
        t = time.perf_counter()
        edits = [e for e in pipe.check(src, use_cloud=use_cloud) if e.confidence >= threshold]
        return apply_edits(src, edits), time.perf_counter() - t
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, texts))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", default="", help="yerel model adı (config'teki llm.model yerine)")
    ap.add_argument("--no-local", action="store_true")
    ap.add_argument("--cloud", default="", help="OpenRouter model kimliği; verilirse bulut da kullanılır")
    ap.add_argument("--no-rules", action="store_true")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--show", action="store_true", help="hatalı tahminleri yazdır")
    a = ap.parse_args()

    pipe = build_pipeline(local_model=a.local or None, local=not a.no_local, cloud_model=a.cloud or None,
                          rules=not a.no_rules)
    gold = [json.loads(line) for line in (HERE / "gold.jsonl").open(encoding="utf-8")]
    movies = [json.loads(line) for line in (HERE / "movie_reviews.jsonl").open(encoding="utf-8")]
    if a.limit:
        gold, movies = gold[:a.limit], movies[:a.limit]

    res = run(pipe, [g["src"] for g in gold], a.threshold, bool(a.cloud), a.workers)
    tp = fp = fn = false_alarm = clean = exact = 0
    for g, (hyp, _) in zip(gold, res):
        want = {e.key for e in diff_edits(g["src"], g["tgt"])}
        got = {e.key for e in diff_edits(g["src"], hyp)}
        tp, fp, fn = tp + len(want & got), fp + len(got - want), fn + len(want - got)
        exact += hyp == g["tgt"]
        if g["src"] == g["tgt"]:
            clean += 1
            false_alarm += hyp != g["src"]
        if a.show and hyp != g["tgt"]:
            print(f"  kaynak : {g['src']}\n  beklenen: {g['tgt']}\n  sistem : {hyp}\n")
    lat = [t for _, t in res]

    texts = [" ".join(m["tokens"]) for m in movies]
    mres = run(pipe, texts, a.threshold, bool(a.cloud), a.workers)
    dtp = dfp = dfn = 0
    for m, src, (hyp, _) in zip(movies, texts, mres):
        offs, pos = [], 0
        for tok in m["tokens"]:
            offs.append((pos, pos + len(tok)))
            pos += len(tok) + 1
        edits = diff_edits(src, hyp)
        flagged = {i for i, (s, e) in enumerate(offs) for ed in edits if s < ed.end and ed.start < e}
        gold_flag = {i for i, lab in enumerate(m["labels"]) if lab}
        dtp, dfp, dfn = dtp + len(flagged & gold_flag), dfp + len(flagged - gold_flag), dfn + len(gold_flag - flagged)

    print(json.dumps({
        "sistem": {"kural": not a.no_rules, "yerel": None if a.no_local else (a.local or "varsayılan"), "bulut": a.cloud or None},
        "altin_set": {"P_R_F05": f05(tp, fp, fn), "tam_dogru": f"{exact}/{len(gold)}",
                      "temizde_yanlis_alarm": f"{false_alarm}/{clean}",
                      "ort_gecikme_sn": round(sum(lat) / len(lat), 2) if lat else None},
        "film_yorumlari_tespit": {"P_R_F05": f05(dtp, dfp, dfn)},
        "model_hatalari": len(pipe.errors),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
