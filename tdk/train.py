"""Gece eğitimi: kullanıcı kararları, bulut öğretmen etiketleri ve GECTurk ile LoRA; değerlendirme kapısını geçerse devreye alır."""

import json
import random
import subprocess
import time
import urllib.request
from pathlib import Path

from . import config
from .engines import SYSTEM_PROMPT
from .store import Store

D = config.DATA_DIR
VENV_PY = D / "train-venv/bin/python"
CONVERT = D / "llama.cpp-src/convert_lora_to_gguf.py"
ENV_FILE = config.CONFIG_DIR / "llama.env"
REPO = Path(__file__).resolve().parents[1]
GECTURK = "https://datasets-server.huggingface.co/rows?dataset=mcemilg/GECTurk-generation&config=default&split=train"


def gecturk(n: int) -> list[tuple[str, str]]:
    cache = D / "gecturk.jsonl"
    if not cache.exists():
        rows, rng = [], random.Random(0)
        for off in rng.sample(range(0, 96800, 100), n // 100):
            with urllib.request.urlopen(f"{GECTURK}&offset={off}&length=100", timeout=60) as r:
                rows += [(x["row"]["source"], x["row"]["target"]) for x in json.load(r)["rows"]]
        cache.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in rows), encoding="utf-8")
    return [tuple(json.loads(line)) for line in cache.open(encoding="utf-8")]


def teacher(store: Store) -> list[tuple[str, str]]:
    """Kararı verilmemiş kendi metinlerini bulut modeline (KVKK maskeli) düzelttirir; sonuçlar önbellekte kalır."""
    cache = D / "teacher.jsonl"
    done = {json.loads(line)[0]: json.loads(line)[1] for line in cache.open(encoding="utf-8")} if cache.exists() else {}
    pipe = config.build_pipeline(local=False, rules=False)
    if pipe.cloud:
        todo = [t for (t,) in store.db.execute(
            "SELECT DISTINCT text FROM checks WHERE id NOT IN (SELECT check_id FROM feedback)") if t not in done]
        with cache.open("a", encoding="utf-8") as f:
            for t in todo[:500]:
                try:
                    done[t] = pipe.cloud.correct(t)
                except OSError:
                    continue
                f.write(json.dumps([t, done[t]], ensure_ascii=False) + "\n")
    return list(done.items())


def build_dataset(store: Store, n_gecturk: int) -> dict:
    user = store.training_pairs()
    parts = {"kullanıcı": user * 3, "öğretmen": teacher(store), "gecturk": gecturk(n_gecturk)}
    rows = [{"messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": s},
                          {"role": "assistant", "content": t}]} for p in parts.values() for s, t in p]
    random.Random(1).shuffle(rows)
    (D / "train").mkdir(exist_ok=True)
    (D / "train/train.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                         encoding="utf-8")
    return {k: len(v) for k, v in parts.items()}


def evaluate() -> dict:
    out = subprocess.run(["uv", "run", "--quiet", "python", "eval/run.py", "--threshold", "0.4", "--workers", "4"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    res = json.loads(out[out.index("{"):])
    return {"f05": res["altin_set"]["P_R_F05"][2], "alarm": int(res["altin_set"]["temizde_yanlis_alarm"].split("/")[0]),
            "film_f05": res["film_yorumlari_tespit"]["P_R_F05"][2]}


def set_lora(path: Path | None):
    """llama.env'deki TDK_EXTRA satırını değiştirip yerel modeli yeniden başlatır; diğer satırlar korunur."""
    lines = [x for x in (ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []) if not x.startswith("TDK_EXTRA=")]
    if path:
        lines.append(f"TDK_EXTRA=--lora {path}")
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text("\n".join(lines) + "\n")
    subprocess.run(["systemctl", "--user", "restart", "tdk-llama.service"], check=True)
    for _ in range(120):
        try:
            urllib.request.urlopen("http://127.0.0.1:8091/health", timeout=2)
            return
        except OSError:
            time.sleep(2)
    raise RuntimeError("yerel model yeniden başlamadı")


def run(dry_run: bool = False):
    cfg = config.load()["train"]
    store = Store(D / "tdk.db")
    counts = build_dataset(store, cfg["gecturk"])
    print("eğitim verisi:", counts, flush=True)
    if dry_run:
        return
    stamp = time.strftime("%Y%m%d-%H%M")
    out = D / f"train/lora-{stamp}"
    base_dir = D / "base" / cfg["base_hf"].replace("/", "--")
    if not base_dir.exists():
        dl = "import sys; from huggingface_hub import snapshot_download as s; s(sys.argv[1], local_dir=sys.argv[2])"
        subprocess.run([str(VENV_PY), "-c", dl, cfg["base_hf"], str(base_dir)], check=True)
    subprocess.run([str(VENV_PY), "-m", "tdk.lora", str(base_dir), str(D / "train/train.jsonl"), str(out)],
                   cwd=REPO, check=True)
    gguf = D / f"models/lora-{stamp}.gguf"
    subprocess.run([str(VENV_PY), str(CONVERT), str(out), "--base", str(base_dir), "--outfile", str(gguf)],
                   check=True)
    old = next((x.split("--lora ", 1)[1] for x in (ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else [])
                if x.startswith("TDK_EXTRA=--lora ")), None)
    base = evaluate()
    set_lora(gguf)
    cand = evaluate()
    ok = cand["f05"] >= base["f05"] and cand["alarm"] <= base["alarm"]
    print(f"önceki {base} | aday {cand} | {'devreye alındı' if ok else 'reddedildi'}", flush=True)
    if not ok:
        set_lora(Path(old) if old else None)
    with (D / "train/log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": stamp, "veri": counts, "onceki": base, "aday": cand, "kabul": ok}) + "\n")
