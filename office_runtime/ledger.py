from __future__ import annotations

from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable
import json


class RuntimeLedger:
    """Append-only JSONL evidence ledger.

    The ledger is intentionally small and filesystem-backed so assignments, ACKs,
    heartbeats, evidence and handoffs survive process restarts without requiring
    a new paid service or credential.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    @staticmethod
    def _normalize(value: Any) -> Any:
        if is_dataclass(value):
            return RuntimeLedger._normalize(asdict(value))
        if isinstance(value, dict):
            return {str(k): RuntimeLedger._normalize(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [RuntimeLedger._normalize(v) for v in value]
        if hasattr(value, "value"):
            return value.value
        return value

    def append(self, record_type: str, payload: Any) -> Dict[str, Any]:
        record = {"record_type": record_type, "payload": self._normalize(payload)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
        return record

    def records(self, record_type: str | None = None) -> Iterable[Dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                if record_type is None or record.get("record_type") == record_type:
                    yield record

    def latest(self, record_type: str, key: str, value: str) -> Dict[str, Any] | None:
        match = None
        for record in self.records(record_type):
            if record.get("payload", {}).get(key) == value:
                match = record
        return match
