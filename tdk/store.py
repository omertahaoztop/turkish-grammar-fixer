"""Geri bildirim deposu ve anında öğrenme: kural susturma, reddedilen öneriyi unutma, benzer örnek arama."""

import json
import re
import sqlite3
import threading
import time
from array import array
from math import sqrt
from pathlib import Path

import akana

from .edits import Edit, apply_edits

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (id INTEGER PRIMARY KEY, ts REAL, text TEXT, edits TEXT);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY, ts REAL, check_id INTEGER, original TEXT, replacement TEXT,
  rule TEXT, sources TEXT, decision TEXT CHECK (decision IN ('accept', 'reject')));
CREATE TABLE IF NOT EXISTS examples (id INTEGER PRIMARY KEY, ts REAL, src TEXT UNIQUE, tgt TEXT, vec BLOB);
"""

MUTE_MIN_VOTES = 3
MUTE_ACCEPT_RATE = 0.3
IGNORE_AFTER_REJECTS = 2


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.emb = akana.Embeddings()

    def add_check(self, text: str, edits: list[dict]) -> int:
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO checks (ts, text, edits) VALUES (?, ?, ?)",
                                  (time.time(), text, json.dumps(edits, ensure_ascii=False)))
            return cur.lastrowid

    def feedback(self, check_id: int, accepted: list[int]):
        """accepted: kabul edilen önerilerin sırası; kalanlar ret sayılır."""
        row = self.db.execute("SELECT text, edits FROM checks WHERE id = ?", (check_id,)).fetchone()
        if not row:
            raise KeyError(check_id)
        text, edits = row[0], json.loads(row[1])
        with self.lock, self.db:
            for i, e in enumerate(edits):
                self.db.execute(
                    "INSERT INTO feedback (ts, check_id, original, replacement, rule, sources, decision) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (time.time(), check_id, e["original"], e["replacement"], e["rule"],
                     ",".join(e["sources"]), "accept" if i in accepted else "reject"))
        # Öneri alan her cümle örnek olur; tümü reddedilen cümle "dokunma" örneği olarak da değerlidir.
        for m in re.finditer(r"[^.!?…\n]+[.!?…]*", text):
            a, b = m.start(), m.end()
            inside = [(i, e) for i, e in enumerate(edits) if a <= e["start"] and e["end"] <= b]
            if not inside or not m.group().strip():
                continue
            keep = [Edit(e["start"] - a, e["end"] - a, e["original"], e["replacement"])
                    for i, e in inside if i in accepted]
            self.add_example(m.group().strip(), apply_edits(m.group(), keep).strip())

    def add_example(self, src: str, tgt: str):
        vec = array("f", self.emb.embed(src)).tobytes()
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO examples (ts, src, tgt, vec) VALUES (?, ?, ?, ?)",
                            (time.time(), src, tgt, vec))

    def similar(self, text: str, k: int = 3, min_sim: float = 0.3) -> list[tuple[str, str]]:
        q = self.emb.embed(text)
        qn = sqrt(sum(x * x for x in q)) or 1.0
        scored = []
        for src, tgt, blob in self.db.execute("SELECT src, tgt, vec FROM examples"):
            v = array("f")
            v.frombytes(blob)
            vn = sqrt(sum(x * x for x in v)) or 1.0
            s = sum(x * y for x, y in zip(q, v)) / (qn * vn)
            if s >= min_sim and src != text:
                scored.append((s, src, tgt))
        return [(s, t) for _, s, t in sorted(scored, reverse=True)[:k]]

    def muted_rules(self) -> set[str]:
        rows = self.db.execute(
            "SELECT rule, SUM(decision = 'accept'), COUNT(*) FROM feedback WHERE rule != 'model' GROUP BY rule")
        return {r for r, acc, n in rows if n >= MUTE_MIN_VOTES and acc / n < MUTE_ACCEPT_RATE}

    def ignored_pairs(self) -> set[tuple[str, str]]:
        rows = self.db.execute(
            "SELECT original, replacement FROM feedback GROUP BY original, replacement "
            "HAVING SUM(decision = 'reject') >= ? AND SUM(decision = 'accept') = 0", (IGNORE_AFTER_REJECTS,))
        return set(rows)

    def training_pairs(self) -> list[tuple[str, str]]:
        return list(self.db.execute("SELECT src, tgt FROM examples ORDER BY ts"))

    def stats(self) -> dict:
        def one(sql):
            return self.db.execute(sql).fetchone()[0]
        return {"denetim": one("SELECT COUNT(*) FROM checks"),
                "kabul": one("SELECT COUNT(*) FROM feedback WHERE decision = 'accept'"),
                "ret": one("SELECT COUNT(*) FROM feedback WHERE decision = 'reject'"),
                "ornek": one("SELECT COUNT(*) FROM examples"),
                "susturulan_kurallar": sorted(self.muted_rules())}
