from __future__ import annotations

import csv
import math
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import psutil
from dotenv import load_dotenv
from prometheus_client import Counter, Gauge, start_http_server

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

GPU_INDEX = os.getenv("GPU_INDEX", "0")
PORT = int(os.getenv("EXPORTER_PORT", "9835"))
SAMPLE_INTERVAL = float(os.getenv("SAMPLE_INTERVAL_SECONDS", "1"))
FORCED_MC_PID = os.getenv("MINECRAFT_PID")
PRESENTMON_PATH = os.getenv("PRESENTMON_PATH") or shutil.which("PresentMon.exe") or shutil.which("PresentMon")
DEFAULT_MC_DIR = Path(os.getenv("APPDATA", "")) / ".minecraft" if os.getenv("APPDATA") else Path.home() / ".minecraft"
MINECRAFT_DIR = Path(os.getenv("MINECRAFT_DIR", str(DEFAULT_MC_DIR)))

# ---- Exporter health -------------------------------------------------------
exporter_up = Gauge("gpu_lab_exporter_up", "1 while the exporter sampler loop is healthy")
nvidia_smi_up = Gauge("nvidia_smi_up", "1 when nvidia-smi query succeeds", ["gpu"])
presentmon_up = Gauge("minecraft_presentmon_up", "1 when PresentMon is attached and streaming frames")

# ---- NVIDIA GPU ------------------------------------------------------------
gpu_util = Gauge("nvidia_gpu_utilization_percent", "GPU busy-time utilization reported by nvidia-smi", ["gpu"])
gpu_mem_used = Gauge("nvidia_gpu_memory_used_bytes", "Used framebuffer memory", ["gpu"])
gpu_mem_total = Gauge("nvidia_gpu_memory_total_bytes", "Total framebuffer memory", ["gpu"])
gpu_temp = Gauge("nvidia_gpu_temperature_celsius", "GPU core temperature", ["gpu"])
gpu_power = Gauge("nvidia_gpu_power_draw_watts", "Current GPU board power draw", ["gpu"])
gpu_power_limit = Gauge("nvidia_gpu_power_limit_watts", "Current GPU power limit when exposed by the driver", ["gpu"])
gpu_graphics_clock = Gauge("nvidia_gpu_graphics_clock_mhz", "Current graphics clock", ["gpu"])
gpu_memory_clock = Gauge("nvidia_gpu_memory_clock_mhz", "Current memory clock", ["gpu"])
gpu_pstate = Gauge("nvidia_gpu_pstate", "Numeric NVIDIA P-state: P0 -> 0, P8 -> 8", ["gpu"])

# ---- Host ------------------------------------------------------------------
system_cpu = Gauge("system_cpu_utilization_percent", "Total host CPU utilization")
system_cpu_core = Gauge("system_cpu_core_utilization_percent", "Host CPU utilization per logical core", ["core"])
system_mem_used = Gauge("system_memory_used_bytes", "Host RAM in use")
system_mem_total = Gauge("system_memory_total_bytes", "Total host RAM")
system_mem_percent = Gauge("system_memory_utilization_percent", "Host RAM utilization")
system_disk_read_total = Counter("system_disk_read_bytes", "Host disk bytes read since exporter start")
system_disk_write_total = Counter("system_disk_write_bytes", "Host disk bytes written since exporter start")
system_net_rx_total = Counter("system_network_receive_bytes", "Host network bytes received since exporter start")
system_net_tx_total = Counter("system_network_transmit_bytes", "Host network bytes transmitted since exporter start")
_io_prev: dict[str, int] = {}

# ---- Minecraft process -----------------------------------------------------
mc_up = Gauge("minecraft_process_up", "1 when the Minecraft Java process is detected")
mc_pid_metric = Gauge("minecraft_process_pid", "Detected Minecraft process ID")
mc_cpu = Gauge("minecraft_process_cpu_percent", "Minecraft process CPU utilization; 100% ~= one logical CPU")
mc_rss = Gauge("minecraft_process_resident_memory_bytes", "Minecraft Java process RSS")
mc_render_distance = Gauge("minecraft_option_render_distance_chunks", "Minecraft render distance from options.txt when available")
mc_simulation_distance = Gauge("minecraft_option_simulation_distance_chunks", "Minecraft simulation distance from options.txt when available")
mc_max_fps = Gauge("minecraft_option_max_fps", "Minecraft FPS cap from options.txt when available")
mc_vsync = Gauge("minecraft_option_vsync_enabled", "Minecraft VSync option: 1 enabled, 0 disabled")
mc_entity_distance = Gauge("minecraft_option_entity_distance_scaling", "Minecraft entity distance scaling option when available")

# ---- PresentMon / frame telemetry -----------------------------------------
mc_fps = Gauge("minecraft_fps", "Instantaneous presented FPS derived from msBetweenPresents")
mc_fps_avg = Gauge("minecraft_fps_avg_10s", "FPS derived from mean frame interval over the last 10 seconds")
mc_fps_1pct = Gauge("minecraft_fps_1pct_low", "Approximate 1% low FPS from the 99th percentile frame interval over the last 10 seconds")
mc_frame_ms = Gauge("minecraft_frame_time_ms", "Latest time between Present calls")
mc_frame_p99_ms = Gauge("minecraft_frame_time_p99_ms", "99th percentile present interval over the last 10 seconds")
mc_display_frame_ms = Gauge("minecraft_display_frame_time_ms", "Latest displayed frame interval when available")
mc_display_fps = Gauge("minecraft_display_fps", "Displayed FPS derived from msBetweenDisplayChange when available")
mc_gpu_active_ms = Gauge("minecraft_frame_gpu_active_ms", "GPU active duration attributed to the latest frame by PresentMon")
mc_render_latency_ms = Gauge("minecraft_render_present_latency_ms", "Present-to-render-complete latency from PresentMon")
mc_display_latency_ms = Gauge("minecraft_present_to_display_ms", "Present-to-display latency from PresentMon")
mc_presentmon_age = Gauge("minecraft_presentmon_last_frame_age_seconds", "Age of the last PresentMon frame sample")
mc_frames = Counter("minecraft_frames", "Frames observed by PresentMon")
mc_dropped_frames = Counter("minecraft_dropped_frames", "Dropped frames observed by PresentMon")


def number(value: str) -> Optional[float]:
    value = value.strip()
    if not value or value.upper() in {"N/A", "NA", "[N/A]", "NOT SUPPORTED"}:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", "."))
    return float(m.group(0)) if m else None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return math.nan
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - k) + xs[hi] * (k - lo)


class NvidiaSampler:
    FIELDS = [
        "utilization.gpu",
        "memory.used",
        "memory.total",
        "temperature.gpu",
        "power.draw",
        "power.limit",
        "clocks.current.graphics",
        "clocks.current.memory",
        "pstate",
    ]

    def sample(self) -> None:
        cmd = [
            "nvidia-smi",
            "-i",
            GPU_INDEX,
            "--query-gpu=" + ",".join(self.FIELDS),
            "--format=csv,noheader,nounits",
        ]
        try:
            out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT, timeout=3)
            row = next(csv.reader([out.strip().splitlines()[0]]))
            if len(row) != len(self.FIELDS):
                raise RuntimeError(f"Unexpected nvidia-smi column count: {row!r}")
            data = dict(zip(self.FIELDS, row))
            label = GPU_INDEX

            def set_if(gauge: Gauge, key: str, transform=lambda x: x):
                v = number(data[key])
                if v is not None:
                    gauge.labels(label).set(transform(v))

            set_if(gpu_util, "utilization.gpu")
            set_if(gpu_mem_used, "memory.used", lambda mib: mib * 1024 * 1024)
            set_if(gpu_mem_total, "memory.total", lambda mib: mib * 1024 * 1024)
            set_if(gpu_temp, "temperature.gpu")
            set_if(gpu_power, "power.draw")
            set_if(gpu_power_limit, "power.limit")
            set_if(gpu_graphics_clock, "clocks.current.graphics")
            set_if(gpu_memory_clock, "clocks.current.memory")
            p = data["pstate"].strip().upper()
            if re.fullmatch(r"P\d+", p):
                gpu_pstate.labels(label).set(int(p[1:]))
            nvidia_smi_up.labels(label).set(1)
        except Exception as exc:
            nvidia_smi_up.labels(GPU_INDEX).set(0)
            print(f"[nvidia-smi] {exc}")


class MinecraftProcessFinder:
    def __init__(self) -> None:
        self.proc: Optional[psutil.Process] = None
        self.pid: Optional[int] = None

    @staticmethod
    def _score(proc: psutil.Process) -> int:
        try:
            name = proc.name().lower()
            if name not in {"javaw.exe", "java.exe", "javaw", "java"}:
                return -1
            cmd = " ".join(proc.cmdline()).lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return -1
        score = 1
        if "net.minecraft" in cmd:
            score += 50
        if ".minecraft" in cmd or "minecraft" in cmd:
            score += 30
        if "fabric" in cmd or "forge" in cmd or "lwjgl" in cmd:
            score += 10
        if "runtime-" in cmd:
            score += 5
        return score

    def find(self) -> Optional[psutil.Process]:
        if FORCED_MC_PID:
            try:
                return psutil.Process(int(FORCED_MC_PID))
            except (ValueError, psutil.NoSuchProcess):
                return None

        best: tuple[int, Optional[psutil.Process]] = (-1, None)
        for proc in psutil.process_iter(["pid", "name"]):
            s = self._score(proc)
            if s > best[0]:
                best = (s, proc)
        return best[1] if best[0] > 1 else None

    def sample(self) -> Optional[int]:
        proc = self.find()
        if proc is None:
            self.proc = None
            self.pid = None
            mc_up.set(0)
            mc_pid_metric.set(0)
            mc_cpu.set(0)
            mc_rss.set(0)
            return None

        try:
            if self.pid != proc.pid:
                self.proc = proc
                self.pid = proc.pid
                # Prime psutil's non-blocking CPU counter.
                proc.cpu_percent(interval=None)
                print(f"[minecraft] detected PID {proc.pid}: {proc.name()}")
            assert self.proc is not None
            mc_up.set(1)
            mc_pid_metric.set(proc.pid)
            mc_cpu.set(self.proc.cpu_percent(interval=None))
            mc_rss.set(self.proc.memory_info().rss)
            return proc.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.proc = None
            self.pid = None
            mc_up.set(0)
            return None


class PresentMonReader:
    def __init__(self) -> None:
        self.proc: Optional[subprocess.Popen[str]] = None
        self.pid: Optional[int] = None
        self.session_name: Optional[str] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.frames: deque[tuple[float, float]] = deque()
        self.last_frame_at: Optional[float] = None
        self.lock = threading.Lock()

    @property
    def available(self) -> bool:
        return bool(PRESENTMON_PATH and Path(PRESENTMON_PATH).exists())

    def stop(self) -> None:
        self.stop_event.set()

        proc = self.proc
        session_name = self.session_name

        # Stop the ETW session explicitly before killing the PresentMon process.
        if session_name and PRESENTMON_PATH:
            try:
                result = subprocess.run(
                    [
                        str(PRESENTMON_PATH),
                        "--terminate_existing_session",
                        "--session_name",
                        session_name,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )

                if result.returncode != 0:
                    message = (result.stdout or "").strip()
                    print(
                        f"[presentmon] warning: failed to stop ETW session "
                        f"{session_name}: {message or f'exit code {result.returncode}'}"
                    )

            except Exception as exc:
                print(
                    f"[presentmon] warning: failed to stop ETW session "
                    f"{session_name}: {exc}"
                )

        # Stopping the ETW session should normally make the capture process exit.
        if proc and proc.poll() is None:
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                print(
                    "[presentmon] capture process did not exit after ETW shutdown; "
                    "terminating it"
                )
                proc.terminate()

                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)

        self.proc = None
        self.pid = None
        self.session_name = None
        self.thread = None
        presentmon_up.set(0)

    def ensure(self, pid: Optional[int]) -> None:
        if not self.available or pid is None:
            if self.proc:
                self.stop()
                self.stop_event = threading.Event()
            presentmon_up.set(0)
            return
        if self.pid == pid and self.proc and self.proc.poll() is None:
            return
        if self.proc:
            self.stop()
        self.stop_event = threading.Event()
        self.pid = pid
        self.session_name = f"MinecraftGpuLab_{pid}"

        cmd = [
            str(PRESENTMON_PATH),
            "--process_id",
            str(pid),
            "--output_stdout",
            "--no_console_stats",
            "--v1_metrics",
            "--session_name",
            self.session_name,
            "--stop_existing_session",
        ]
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                creationflags=creationflags,
            )
            self.thread = threading.Thread(target=self._reader_loop, daemon=True)
            self.thread.start()
            print(f"[presentmon] attached to PID {pid}")
        except Exception as exc:
            print(f"[presentmon] failed to start: {exc}")
            self.proc = None
            self.pid = None
            self.session_name = None
            presentmon_up.set(0)

    def _reader_loop(self) -> None:
        assert self.proc and self.proc.stdout
        header: Optional[list[str]] = None
        try:
            for raw in self.proc.stdout:
                if self.stop_event.is_set():
                    break
                line = raw.strip().lstrip("\ufeff")
                if not line:
                    continue
                if line.startswith("Application,"):
                    header = next(csv.reader([line]))
                    presentmon_up.set(1)
                    print("[presentmon] CSV stream started")
                    continue
                if header is None:
                    print(f"[presentmon] {line}")
                    continue
                try:
                    values = next(csv.reader([line]))
                    if len(values) != len(header):
                        continue
                    row = dict(zip(header, values))
                    self._consume(row)
                except Exception as exc:
                    print(f"[presentmon] row parse error: {exc}")
        finally:
            presentmon_up.set(0)

    def _consume(self, row: dict[str, str]) -> None:
        frame_ms = number(row.get("msBetweenPresents", ""))
        if frame_ms is None or frame_ms <= 0:
            return
        now = time.monotonic()
        with self.lock:
            self.frames.append((now, frame_ms))
            cutoff = now - 10.0
            while self.frames and self.frames[0][0] < cutoff:
                self.frames.popleft()
            intervals = [x[1] for x in self.frames if x[1] > 0]
            self.last_frame_at = now

        mc_frames.inc()
        dropped = row.get("Dropped", "").strip().lower()
        if dropped in {"1", "true", "dropped", "yes"}:
            mc_dropped_frames.inc()

        mc_frame_ms.set(frame_ms)
        mc_fps.set(1000.0 / frame_ms)
        if intervals:
            mean_ms = sum(intervals) / len(intervals)
            p99 = percentile(intervals, 0.99)
            mc_fps_avg.set(1000.0 / mean_ms)
            mc_frame_p99_ms.set(p99)
            if p99 > 0:
                mc_fps_1pct.set(1000.0 / p99)

        display_ms = number(row.get("msBetweenDisplayChange", ""))
        if display_ms and display_ms > 0:
            mc_display_frame_ms.set(display_ms)
            mc_display_fps.set(1000.0 / display_ms)

        gpu_ms = number(row.get("msGPUActive", ""))
        if gpu_ms is not None:
            mc_gpu_active_ms.set(gpu_ms)
        render_ms = number(row.get("msUntilRenderComplete", ""))
        if render_ms is not None:
            mc_render_latency_ms.set(render_ms)
        display_latency = number(row.get("msUntilDisplayed", ""))
        if display_latency is not None:
            mc_display_latency_ms.set(display_latency)

    def sample_age(self) -> None:
        with self.lock:
            if self.last_frame_at is None:
                mc_presentmon_age.set(float("nan"))
            else:
                mc_presentmon_age.set(max(0.0, time.monotonic() - self.last_frame_at))



def sample_minecraft_options() -> None:
    path = MINECRAFT_DIR / "options.txt"
    if not path.exists():
        return
    try:
        options: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            options[key.strip()] = value.strip()

        def set_num(gauge: Gauge, *keys: str) -> None:
            for key in keys:
                if key in options:
                    try:
                        gauge.set(float(options[key]))
                    except ValueError:
                        pass
                    return

        set_num(mc_render_distance, "renderDistance")
        set_num(mc_simulation_distance, "simulationDistance")
        set_num(mc_max_fps, "maxFps")
        set_num(mc_entity_distance, "entityDistanceScaling")
        for key in ("enableVsync", "vsync"):
            if key in options:
                mc_vsync.set(1 if options[key].lower() == "true" else 0)
                break
    except Exception as exc:
        print(f"[minecraft-options] {exc}")

def sample_host() -> None:
    core = psutil.cpu_percent(interval=None, percpu=True)
    if core:
        system_cpu.set(sum(core) / len(core))
        for i, value in enumerate(core):
            system_cpu_core.labels(str(i)).set(value)
    vm = psutil.virtual_memory()
    system_mem_used.set(vm.used)
    system_mem_total.set(vm.total)
    system_mem_percent.set(vm.percent)
    disk = psutil.disk_io_counters()
    if disk:
        prev = _io_prev.get("disk_read")
        if prev is not None and disk.read_bytes >= prev:
            system_disk_read_total.inc(disk.read_bytes - prev)
        _io_prev["disk_read"] = disk.read_bytes
        prev = _io_prev.get("disk_write")
        if prev is not None and disk.write_bytes >= prev:
            system_disk_write_total.inc(disk.write_bytes - prev)
        _io_prev["disk_write"] = disk.write_bytes
    net = psutil.net_io_counters()
    if net:
        prev = _io_prev.get("net_rx")
        if prev is not None and net.bytes_recv >= prev:
            system_net_rx_total.inc(net.bytes_recv - prev)
        _io_prev["net_rx"] = net.bytes_recv
        prev = _io_prev.get("net_tx")
        if prev is not None and net.bytes_sent >= prev:
            system_net_tx_total.inc(net.bytes_sent - prev)
        _io_prev["net_tx"] = net.bytes_sent


def main() -> None:
    psutil.cpu_percent(interval=None, percpu=True)
    finder = MinecraftProcessFinder()
    nvidia = NvidiaSampler()
    presentmon = PresentMonReader()

    start_http_server(PORT, addr="0.0.0.0")
    print(f"[exporter] metrics: http://localhost:{PORT}/metrics")

    if PRESENTMON_PATH:
        print(f"[presentmon] configured: {PRESENTMON_PATH}")
    else:
        print("[presentmon] not configured; FPS/frametime metrics will stay unavailable")

    try:
        while True:
            started = time.monotonic()

            try:
                sample_host()
                sample_minecraft_options()
                pid = finder.sample()
                nvidia.sample()
                presentmon.ensure(pid)
                presentmon.sample_age()
                exporter_up.set(1)
            except Exception as exc:
                exporter_up.set(0)
                print(f"[exporter] sampler error: {exc}")

            elapsed = time.monotonic() - started
            time.sleep(max(0.05, SAMPLE_INTERVAL - elapsed))

    except KeyboardInterrupt:
        print("\n[exporter] stopping...")

    finally:
        presentmon.stop()
        print("[presentmon] stopped")


if __name__ == "__main__":
    main()
