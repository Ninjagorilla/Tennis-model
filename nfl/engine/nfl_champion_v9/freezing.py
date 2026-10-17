"""Exclusive, timestamped research snapshots. No unverified live certification."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def code_hashes() -> dict[str, str]:
    return {p.name: sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}


def utc(value: str) -> datetime:
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError("Invalid timestamp") from exc
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("Timezone-aware timestamp required")
    return d.astimezone(timezone.utc)


def check_receipt(receipt: dict, now: datetime, *, max_age_seconds: float = 60) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Clock must be timezone-aware")
    if receipt.get("status") != "scheduled":
        raise ValueError("Started, completed, canceled or unknown event status")
    if not isinstance(receipt.get("source_refs"), list) or not receipt["source_refs"] or not all(isinstance(x, str) and x.strip() for x in receipt["source_refs"]):
        raise ValueError("Source references required; their presence alone is not verification")
    if not isinstance(receipt.get("event_id"), str) or not receipt["event_id"].strip():
        raise ValueError("Event identity required")
    if now >= utc(receipt["kickoff_utc"]):
        raise ValueError("Cannot create a pregame snapshot at/after kickoff")
    age = (now - utc(receipt["status_checked_at_utc"])).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise ValueError("Future-dated or stale event-status evidence")


def freeze(path: str | Path, prediction: dict, input_data: dict, receipt_provider,
           *, clock=None) -> dict:
    """Check a fresh receipt before serializing and again immediately before write.

    A receipt_provider must acquire its own actual event status. This library does
    not independently verify the supplied provider. Snapshots remain research.
    clock injection is for tests; the CLI never accepts a caller-specified clock.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    first = receipt_provider()
    check_receipt(first, clock())
    second = receipt_provider()
    now = clock()
    check_receipt(second, now)
    if first["event_id"] != second["event_id"] or first["kickoff_utc"] != second["kickoff_utc"]:
        raise ValueError("Fixture identity or kickoff changed during run")
    if prediction.get("event_id") != second["event_id"] or input_data.get("event_id") != second["event_id"]:
        raise ValueError("Prediction/input/fixture identity mismatch")
    payload = {"schema": "nfl-v9-research-freeze-1", "recorded_at_utc": now.isoformat(),
               "evidence_class": "TEST_ONLY" if prediction.get("kind") == "TEST_ONLY" else "RESEARCH_PRE_EVENT_NOT_CERTIFIED",
               "prediction": prediction, "input_data": input_data, "status_receipt": second,
               "code_hashes": code_hashes()}
    artifact = {"payload": payload, "sha256": sha256(canonical(payload)).hexdigest()}
    encoded = canonical(artifact) + b"\n"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Recheck time after serialization. O_EXCL prevents clobbering an existing freeze.
    check_receipt(second, clock())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    return artifact


def verify(path: str | Path) -> bool:
    obj = json.loads(Path(path).read_text())
    return sha256(canonical(obj["payload"])).hexdigest() == obj["sha256"]
