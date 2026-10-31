"""tdkd: modeli ve kural motorunu sıcak tutan yerel HTTP servisi (yalnız 127.0.0.1)."""

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .cli import PORT
from .edits import apply_edits
from .store import Store


class Service:
    def __init__(self):
        self.cfg = config.load()
        self.pipe = config.build_pipeline()
        self.store = Store(config.DATA_DIR / "tdk.db")

    def check(self, text: str, cloud: bool = False, fast: bool = False) -> dict:
        errors: list[str] = []
        if fast:
            edits = self.pipe.check(text, fast=True)
        else:
            examples = self.store.similar(text) if self.pipe.llm else []
            edits = self.pipe.check(text, use_cloud=cloud, examples=examples, errors=errors)
            # Yerel model yanıt vermediyse ve bulut açıksa yedek olarak bulut kullanılır.
            if not cloud and self.pipe.cloud and any(e.startswith("yerel") for e in errors):
                edits = self.pipe.check(text, use_cloud=True, examples=examples, errors=errors)
        muted, ignored = self.store.muted_rules(), self.store.ignored_pairs()
        edits = [e for e in edits if e.rule not in muted and (e.original, e.replacement) not in ignored]
        out = [asdict(e) for e in edits]
        cid = self.store.add_check(text, out)
        auto = [e for e in edits if e.confidence >= self.cfg["apply_threshold"]]
        return {"id": cid, "edits": out, "corrected": apply_edits(text, auto), "errors": errors,
                "threshold": self.cfg["apply_threshold"]}


def serve(port: int = PORT):
    svc = Service()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, obj):
            body = json.dumps(obj, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"ok": True})
            if self.path == "/stats":
                return self._send(200, svc.store.stats())
            self._send(404, {"error": "yok"})

        def do_POST(self):
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/check":
                    return self._send(200, svc.check(req["text"], bool(req.get("cloud")), bool(req.get("fast"))))
                if self.path == "/feedback":
                    svc.store.feedback(int(req["id"]), [int(i) for i in req.get("accepted", [])])
                    return self._send(200, {"ok": True})
                if self.path == "/reload":
                    svc.pipe.rules and svc.pipe.rules.reload()
                    return self._send(200, {"ok": True})
                self._send(404, {"error": "yok"})
            except (KeyError, ValueError, TypeError) as e:
                self._send(400, {"error": f"geçersiz istek: {e}"})

        def log_message(self, *args):
            pass

    print(f"tdkd 127.0.0.1:{port} dinliyor", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
