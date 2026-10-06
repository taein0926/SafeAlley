"""Observe a real Qwen/DB query through the frontend proxy."""

import argparse
import json
from time import perf_counter
from urllib.request import Request, urlopen


DEMO_QUERY = (
    "밤 10시에 정부인천지방합동청사에서 두리하나어린이집까지 "
    "가로등과 CCTV가 많은 길로 안내해줘. 계단은 피하고 건널목은 적게 지나고 싶어"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://frontend/api/agent/query/stream")
    parser.add_argument("--query", default=DEMO_QUERY)
    args = parser.parse_args()
    request = Request(args.url, data=json.dumps({
"query": args.query, "source": "osm",
    }, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    started = perf_counter()
    result = None
    progress = []
    with urlopen(request, timeout=360) as response:
        for line in response:
            if not line.strip():
                continue
            event = json.loads(line)
            elapsed = round(perf_counter() - started, 2)
            if event["type"] == "error":
                raise RuntimeError(event["detail"])
            if event["type"] == "route_progress":
                progress.append({"elapsed_s": elapsed, **event["data"]})
                print(json.dumps(progress[-1], ensure_ascii=False), flush=True)
            elif event["type"] == "result":
                result = event["data"]
    if result is None or not progress:
        raise RuntimeError("No result or routing progress received")
    print(json.dumps({
        "elapsed_s": round(perf_counter() - started, 2),
        "preferences": result["interpretation"]["preferences"],
        "recommendation_status": result["result"]["recommendation_status"],
        "candidate_count": len(result["result"]["candidates"]),
        "selected_route": result["result"]["selected_route_type"],
        "model": result["model"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
