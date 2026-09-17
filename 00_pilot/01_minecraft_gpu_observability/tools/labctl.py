from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

GRAFANA_URL = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
PASSWORD = os.getenv("GRAFANA_ADMIN_PASSWORD", "change-me-local-only")
DASHBOARD_UID = os.getenv("GRAFANA_DASHBOARD_UID", "minecraft-gpu-lab")
STATE_DIR = ROOT / ".lab"
RUNS_DIR = ROOT / "runs"
CURRENT = STATE_DIR / "current_run.json"


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "run"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_current() -> dict | None:
    if not CURRENT.exists():
        return None
    return json.loads(CURRENT.read_text(encoding="utf-8"))


def save_current(data: dict) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    CURRENT.write_text(json.dumps(data, indent=2), encoding="utf-8")


def log_event(payload: dict) -> None:
    run = load_current()
    RUNS_DIR.mkdir(exist_ok=True)
    run_id = run["run_id"] if run else "unscoped"
    with (RUNS_DIR / f"{run_id}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def annotate(text: str, tags: list[str]) -> None:
    run = load_current()
    merged_tags = ["minecraft", "gpu-lab", *tags]
    if run:
        merged_tags += [f"run:{run['run_id']}", f"scenario:{run['scenario_slug']}"]
    body = {
        "dashboardUID": DASHBOARD_UID,
        "time": int(datetime.now().timestamp() * 1000),
        "tags": sorted(set(merged_tags)),
        "text": text,
    }
    r = requests.post(
        f"{GRAFANA_URL}/api/annotations",
        auth=(USER, PASSWORD),
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=5,
    )
    r.raise_for_status()
    record = {"at": now_iso(), "kind": "annotation", **body}
    log_event(record)
    print(f"annotation: {text}")


def cmd_start(args: argparse.Namespace) -> None:
    existing = load_current()
    if existing:
        raise SystemExit(f"A run is already active: {existing['run_id']} ({existing['scenario']})")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run = {
        "run_id": f"{stamp}-{slug(args.scenario)}",
        "scenario": args.scenario,
        "scenario_slug": slug(args.scenario),
        "started_at": now_iso(),
        "notes": args.notes or "",
    }
    save_current(run)
    annotate(f"RUN START — {args.scenario}" + (f" — {args.notes}" if args.notes else ""), ["run-start", *args.tags])
    print(json.dumps(run, indent=2, ensure_ascii=False))


def cmd_event(args: argparse.Namespace) -> None:
    annotate(args.text, ["event", *args.tags])


def cmd_nsight(args: argparse.Namespace) -> None:
    label = args.label or "frame capture"
    annotate(f"NSIGHT CAPTURE — {label}", ["nsight", "capture", *args.tags])


def cmd_stop(args: argparse.Namespace) -> None:
    run = load_current()
    if not run:
        raise SystemExit("No active run.")
    annotate(f"RUN STOP — {run['scenario']}" + (f" — {args.notes}" if args.notes else ""), ["run-stop"])
    finished = {**run, "stopped_at": now_iso(), "stop_notes": args.notes or ""}
    (RUNS_DIR / f"{run['run_id']}.summary.json").write_text(json.dumps(finished, indent=2, ensure_ascii=False), encoding="utf-8")
    CURRENT.unlink(missing_ok=True)
    print(json.dumps(finished, indent=2, ensure_ascii=False))


def cmd_status(_args: argparse.Namespace) -> None:
    print(json.dumps(load_current() or {"active": False}, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Minecraft GPU lab run/event controller")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="Start an experiment run and annotate Grafana")
    p.add_argument("scenario")
    p.add_argument("--notes")
    p.add_argument("--tags", nargs="*", default=[])
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("event", help="Create a timestamped Grafana annotation")
    p.add_argument("text")
    p.add_argument("--tags", nargs="*", default=[])
    p.set_defaults(func=cmd_event)

    p = sub.add_parser("nsight", help="Mark the instant at which you take an Nsight capture")
    p.add_argument("label", nargs="?")
    p.add_argument("--tags", nargs="*", default=[])
    p.set_defaults(func=cmd_nsight)

    p = sub.add_parser("stop", help="Stop the current run")
    p.add_argument("--notes")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("status", help="Show current run")
    p.set_defaults(func=cmd_status)

    args = parser.parse_args()
    try:
        args.func(args)
    except requests.RequestException as exc:
        print(f"Grafana API error: {exc}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
