"""Tiny Windows event console. Keep it open beside Minecraft and press a key after an action."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LABCTL = ROOT / "tools" / "labctl.py"

EVENTS = {
    "1": ("Shaders ON", ["shader", "on"]),
    "2": ("Shaders OFF", ["shader", "off"]),
    "3": ("Elytra start", ["elytra", "start"]),
    "4": ("Teleport", ["teleport"]),
    "5": ("Dimension change", ["dimension"]),
    "6": ("Entity stress start", ["entities", "start"]),
    "7": ("Render-distance change", ["render-distance"]),
    "8": ("Nsight capture", ["nsight", "capture"]),
}


def send(text: str, tags: list[str]) -> None:
    cmd = [sys.executable, str(LABCTL), "event", text, "--tags", *tags]
    subprocess.run(cmd, cwd=ROOT, check=False)


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("This convenience console uses Windows msvcrt.")
    import msvcrt

    print("Minecraft GPU Lab event console")
    for key, (text, _) in EVENTS.items():
        print(f"  {key}: {text}")
    print("  q: quit")
    while True:
        key = msvcrt.getwch().lower()
        if key == "q":
            return
        if key in EVENTS:
            text, tags = EVENTS[key]
            send(text, tags)
            print(f"  -> {text}")


if __name__ == "__main__":
    main()
