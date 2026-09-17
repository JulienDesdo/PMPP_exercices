# Deeper profiling

The dashboard is meant to tell us **when** something interesting happens and which parts of the system move with it. It is not supposed to explain every detail of what the GPU is doing internally.

That is where PresentMon and Nsight become useful.

## From `nvidia-smi` to frame-level data

`nvidia-smi` is useful for basic GPU state:

- utilization
- power
- clocks
- temperature
- VRAM
- P-State

These values are useful context, but they are sampled at the GPU/driver level. They do not tell us exactly what happened during a particular frame.

PresentMon adds that missing layer.

For every presented frame, it can expose timing information such as:

- time between presents
- GPU-active time
- time until rendering completes
- time until the frame is displayed

This is particularly useful when the average FPS looks fine but the game still feels uneven.

For example:

```text
7.0 ms
7.2 ms
6.9 ms
54.0 ms
7.1 ms
```

The fourth frame is the interesting one. A dashboard can show that a hitch occurred around that moment; frame-level data lets us identify how abnormal the frame actually was.

## Where Nsight fits

Nsight is not another monitoring layer.

A typical investigation starts with Grafana and only goes deeper when there is something worth explaining:

```text
Minecraft run
    |
    v
Grafana
find the interesting period
    |
    v
PresentMon
inspect frame timing
    |
    v
Nsight
inspect what happened in more detail
```

**Nsight Systems** is useful when the question is about timing across several frames: CPU work, GPU execution, waits, stalls or the relationship between the application and the graphics driver.

**Nsight Graphics** is useful when the question becomes specific to the rendering workload itself: draw calls, shaders, resources, render targets or pipeline state.

There is no reason to use Nsight for every experiment. If the dashboard already shows that the interesting behavior is outside the graphics workload, a frame debugger is probably not the next useful tool.

## Nsight Graphics with Minecraft

Minecraft is not launched directly by a simple fixed executable path: the launcher selects a Java runtime and starts the actual game process.

Because of that, attaching or launching Minecraft through Nsight is intentionally left manual.

A typical workflow is:

1. reproduce the interesting condition first with the normal observability lab;
2. identify what should be captured;
3. launch or attach to the Minecraft graphics process through Nsight Graphics;
4. reproduce the same condition;
5. capture the relevant frame or period;
6. compare the profiler result with the system-level evidence already collected.

An annotation can be added at the capture point with:

```powershell
python tools\labctl.py nsight "short description"
```

The purpose is not to make Nsight part of the monitoring stack. It is the tool used when the monitoring stack has already given us a reason to look deeper.

## Beyond "GPU utilization"

There is no single metric that represents how "full" a GPU is.

A workload can be limited by shader execution, memory bandwidth, cache behavior, texture work or another part of the graphics pipeline while other units remain underused.

That is why deeper profiling eventually moves toward metrics such as hardware-unit throughput, executed shader work and per-frame GPU cost instead of relying only on the `GPU-Util` percentage exposed by `nvidia-smi`.