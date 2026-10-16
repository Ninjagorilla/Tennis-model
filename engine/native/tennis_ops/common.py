from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for directory in ('vendor/sr', 'vendor/legacy781', 'recovery_resolver'):
    sys.path.insert(0, str(ROOT / directory))


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp(text: str) -> datetime:
    if not isinstance(text, str) or 'T' not in text:
        raise ValueError('EXPLICIT_ISO_TIMESTAMP_REQUIRED')
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('TIMEZONE_REQUIRED')
    return value.astimezone(timezone.utc)


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    raw = value if isinstance(value, bytes) else canonical(value).encode()
    return hashlib.sha256(raw).hexdigest()


def filehash(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def key(name: str) -> str:
    name = unicodedata.normalize('NFKD', str(name))
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in name if not unicodedata.combining(c)).lower()).strip()


def relative_path(relative: str, root: Path = ROOT) -> Path:
    p = (root / relative).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError('PATH_OUTSIDE_RUNTIME')
    return p


def safe_id(text: str) -> str:
    if not isinstance(text, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', text):
        raise ValueError('INVALID_REQUEST_ID')
    return text


def probability(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('FINITE_PROBABILITY_REQUIRED')
    return float(value)


def no_market_fields(value: Any) -> None:
    forbidden = {'odds', 'market_price', 'market_probability', 'public_percentage',
                 'decimal_a', 'decimal_b', 'bookmaker_probability', 'implied_probability'}
    if isinstance(value, dict):
        for k, v in value.items():
            if str(k).lower() in forbidden:
                raise ValueError('MARKET_INPUT_FORBIDDEN')
            no_market_fields(v)
    elif isinstance(value, list):
        for v in value:
            no_market_fields(v)


def clean(value: Any) -> Any:
    """Convert numerical library values to finite JSON, preserving missing as null."""
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if hasattr(value, 'item'):
        return clean(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def write_new(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(clean(value), stream, indent=2, ensure_ascii=False, allow_nan=False)


def active_registration() -> Path:
    """Resolve the explicitly saved state pointer, with a checksum, not a version label."""
    pointer = json.loads((ROOT / 'ACTIVE_STATE.json').read_text())
    if pointer.get('schema') != 'tennis-active-state-v1':
        raise ValueError('ACTIVE_STATE_SCHEMA_MISMATCH')
    path = relative_path(pointer['registration_file'])
    if filehash(path) != pointer['registration_sha256']:
        raise ValueError('ACTIVE_STATE_HASH_MISMATCH')
    return path
