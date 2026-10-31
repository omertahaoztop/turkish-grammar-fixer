"""tdk komut satırı: check, serve, stats, popup, train."""

import argparse
import json
import sys
import urllib.error
import urllib.request

PORT = 8092

URL = f"http://127.0.0.1:{PORT}"


def call(path: str, body: dict | None = None, timeout: float = 180) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def check(text: str, cloud: bool = False, fast: bool = False) -> dict:
    try:
        return call("/check", {"text": text, "cloud": cloud, "fast": fast})
    except urllib.error.URLError:
        # Servis kapalıysa aynı işi süreç içinde yapar; ilk açılış birkaç saniye sürer.
        from .server import Service
        return Service().check(text, cloud, fast)


def main():
    ap = argparse.ArgumentParser(prog="tdk", description="Türkçe yazım denetleyici")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="metni denetle (argüman ya da stdin)")
    c.add_argument("text", nargs="*")
    c.add_argument("-c", "--cloud", action="store_true", help="bulut modeli de kullan")
    c.add_argument("-f", "--fast", action="store_true", help="yalnız kurallar; model beklenmez")
    c.add_argument("--json", action="store_true")
    c.add_argument("--fix", action="store_true", help="yalnız düzeltilmiş metni yaz")
    sub.add_parser("serve", help="tdkd servisini başlat")
    sub.add_parser("stats", help="öğrenme istatistikleri")
    p = sub.add_parser("popup", help="seçili metni denetle ve açılır pencerede göster")
    p.add_argument("--auto", action="store_true", help="pencere açmadan yüksek güvenli düzeltmeleri uygula")
    t = sub.add_parser("train", help="biriken örneklerle yerel modele ince ayar")
    t.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.cmd == "serve":
        from .server import serve
        serve()
    elif a.cmd == "stats":
        try:
            stats = call("/stats")
        except urllib.error.URLError:
            from . import config
            from .store import Store
            stats = Store(config.DATA_DIR / "tdk.db").stats()
        print(json.dumps(stats, ensure_ascii=False, indent=1))
    elif a.cmd == "check":
        text = " ".join(a.text) if a.text else sys.stdin.read()
        res = check(text, a.cloud, a.fast)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=1))
        elif a.fix:
            sys.stdout.write(res["corrected"])
        else:
            for e in res["edits"]:
                print(f"{e['original']!r} -> {e['replacement']!r}  [{e['confidence']:.2f} {'+'.join(e['sources'])}]"
                      + (f"  {e['explanation']}" if e["explanation"] else ""))
            for err in res["errors"]:
                print(f"uyarı: {err}", file=sys.stderr)
    elif a.cmd == "popup":
        from .popup import run
        run(auto=a.auto)
    elif a.cmd == "train":
        from .train import run
        run(dry_run=a.dry_run)
