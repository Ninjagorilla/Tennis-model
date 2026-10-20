"""Immutable, market-isolated evidence ledger with deterministic integrity hashes."""
import hashlib,json
from datetime import datetime

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)

def freeze_forecast(forecast,evidence,market=None):
    asof=datetime.fromisoformat(forecast["asof_utc"].replace("Z","+00:00"))
    tip=datetime.fromisoformat(forecast["tipoff_utc"].replace("Z","+00:00"))
    if asof.tzinfo is None or tip.tzinfo is None or asof>tip:
        raise ValueError("Forecast must be frozen before tipoff")
    if not evidence or not evidence.get("source") or not evidence.get("retrieved_at_utc"):
        raise ValueError("Evidence provenance required")
    retrieved=datetime.fromisoformat(evidence["retrieved_at_utc"].replace("Z","+00:00"))
    if retrieved.tzinfo is None or retrieved>asof:
        raise ValueError("Evidence arrived after prediction")
    pure={k:v for k,v in forecast.items() if not k.startswith("market_")}
    record={"forecast":pure,"evidence":evidence}
    digest=hashlib.sha256(canonical(record).encode()).hexdigest()
    return {"forecast_id":digest,"frozen":record,"market_snapshot":market,
            "market_isolated":True,"status":"RESEARCH_UNCALIBRATED"}
