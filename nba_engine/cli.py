"""Usage: python -m nba_engine.cli fixtures.json > nba_scan.json

Input is a JSON array of pregame Game dictionaries. Never substitutes defaults
for missing ratings or claims a live data feed.
"""
import json
import sys
from .core import scan_json

def main():
    with open(sys.argv[1], encoding="utf-8") as f:
        fixtures=json.load(f)
    if not isinstance(fixtures,list):
        raise ValueError("Input must be a list of fixtures")
    output=[]
    seen=set()
    for g in fixtures:
        key=g["game_id"]
        if key in seen:
            raise ValueError("Duplicate fixture ID")
        seen.add(key)
        output.append(scan_json(g))
    print(json.dumps(output,indent=2))

if __name__=="__main__":
    main()
