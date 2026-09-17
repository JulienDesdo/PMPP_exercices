import psutil

candidates = []
for p in psutil.process_iter(["pid", "name", "cmdline"]):
    try:
        name = (p.info["name"] or "").lower()
        if name in {"javaw.exe", "java.exe", "javaw", "java"}:
            cmd = " ".join(p.info["cmdline"] or [])
            candidates.append((p.info["pid"], p.info["name"], cmd))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

if not candidates:
    print("No java/javaw process found.")
else:
    for pid, name, cmd in candidates:
        print(f"PID {pid:>7}  {name}")
        print(f"  {cmd[:500]}")
        print()
    print("If auto-detection is wrong, put MINECRAFT_PID=<pid> in .env and restart the exporter.")
