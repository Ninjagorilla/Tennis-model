"""Usage: python -m first_td_challenger predict INPUT.json [--output FILE.json]."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .core import predict
from .adapter import audit_v91_snapshot
from .settlement import grade
from .markets import quoted_parlay_arithmetic


def main() -> int:
    parser = argparse.ArgumentParser(description="First-TD research core; no live betting or calibration claim")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("predict", "grade"):
        p = sub.add_parser(name)
        p.add_argument("input", type=Path)
        p.add_argument("--output", type=Path)
    p = sub.add_parser("audit-archive")
    p.add_argument("input", type=Path); p.add_argument("--player", required=True)
    p.add_argument("--event-id"); p.add_argument("--output", type=Path)
    p = sub.add_parser("video-price-math")
    p.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "predict":
            result = predict(json.loads(args.input.read_text()))
        elif args.command == "grade":
            body = json.loads(args.input.read_text())
            result = grade(body["selection"], body["event"], body["plays"])
        elif args.command == "audit-archive":
            result = audit_v91_snapshot(args.input, args.player, expected_event_id=args.event_id)
        else:
            result = quoted_parlay_arithmetic([1300, 1500, 700], 20)
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x") as out:
                out.write(encoded)
        else:
            print(encoded, end="")
        return 0
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
