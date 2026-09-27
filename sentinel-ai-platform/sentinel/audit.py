"""Tamper-evident audit log.

Every event is appended as one JSON line carrying the SHA-256 hash of the previous line, so any
edit, deletion or re-ordering breaks the chain and is detected by verify(). In production, ship
the same records to WORM storage (immutable blob / bucket retention lock).
"""
import hashlib, json, threading, time, uuid
from pathlib import Path

GENESIS = "0" * 64


def _digest(prev: str, body: dict) -> str:
    return hashlib.sha256((prev + json.dumps(body, sort_keys=True, separators=(",", ":"))).encode()).hexdigest()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._prev, self._seq = GENESIS, 0
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                rec = json.loads(line)
                self._prev, self._seq = rec["hash"], rec["seq"]

    def append(self, event_type: str, **fields) -> dict:
        with self._lock:
            body = {"seq": self._seq + 1, "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event_id": uuid.uuid4().hex[:12],
                    "type": event_type, **fields, "prev_hash": self._prev}
            body["hash"] = _digest(self._prev, body)
            with self.path.open("a") as fh:
                fh.write(json.dumps(body, sort_keys=True) + "\n")
            self._prev, self._seq = body["hash"], body["seq"]
            return body

    def records(self):
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def verify(self):
        """Return (ok, number_of_records, first_broken_seq_or_None)."""
        prev, n = GENESIS, 0
        for rec in self.records():
            n += 1
            body = {k: v for k, v in rec.items() if k != "hash"}
            if rec.get("prev_hash") != prev or _digest(prev, body) != rec.get("hash"):
                return False, n, rec.get("seq")
            prev = rec["hash"]
        return True, n, None
