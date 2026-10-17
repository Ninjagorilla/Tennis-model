from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from .td import TDRequest, predict
from .freezing import canonical, freeze, verify, code_hashes


def td_main() -> int:
    parser = argparse.ArgumentParser(description="NFL v9.0 implemented TD component; not the full engine")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("td", help="Predict TDs from explicit scenario inputs")
    run.add_argument("--input", required=True)
    run.add_argument("--output", required=True)
    run.add_argument("--fixture-receipt", help="Optional caller-supplied status JSON; not independently verified")
    check = sub.add_parser("verify")
    check.add_argument("path")
    sub.add_parser("status")
    args = parser.parse_args()
    try:
        if args.command == "status":
            registry = Path(__file__).resolve().parents[1] / "CHAMPION_REBUILD_MASTER_REGISTRY.json"
            print(registry.read_text())
        elif args.command == "verify":
            ok = verify(args.path)
            print("HASH_VERIFIED" if ok else "HASH_MISMATCH")
            return 0 if ok else 1
        else:
            data = json.loads(Path(args.input).read_text())
            result = predict(TDRequest.from_dict(data))
            if args.fixture_receipt:
                receipt_path = Path(args.fixture_receipt)
                freeze(args.output, result, data, lambda: json.loads(receipt_path.read_text()))
            else:
                payload = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                           "evidence_class": "TEST_ONLY" if data["kind"] == "TEST_ONLY" else "RESEARCH_TIME_UNVERIFIED",
                           "prediction": result, "input_data": data, "code_hashes": code_hashes()}
                artifact = {"payload": payload, "sha256": hashlib.sha256(canonical(payload)).hexdigest()}
                path = Path(args.output)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("x") as f:
                    f.write(json.dumps(artifact, indent=2, allow_nan=False) + "\n")
            print(f"Saved: {args.output}")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    if len(sys.argv)>1 and sys.argv[1] in ['td','verify']:
        raise SystemExit(td_main())
    from .cli import main
    raise SystemExit(main())
