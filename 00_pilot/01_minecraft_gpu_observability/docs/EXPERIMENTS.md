# Experiments

The point of these experiments is to put pressure on a different part of the system, which gives us a better chance of understanding where a performance problem actually comes from.

## 1. Fast Elytra flight + high render distance

**Question:** when the game stutters while new terrain arrives, is the bottleneck GPU rendering or CPU/chunk work?

Flying quickly with a large render distance is interesting because Minecraft has to keep bringing new terrain into the scene instead of working with a mostly stable view. Chunk loading and generation, CPU-side world processing, disk activity and rendering can all overlap during the same period.

The useful part of the experiment is therefore to compare frame time and 1% low with GPU activity, per-core CPU usage, Minecraft process CPU, disk throughput and the current render distance. The goal is to see which parts of the system change at the same time as the visible stutter, rather than treating the FPS drop itself as evidence of a GPU problem.

## 2. Entity-heavy scene

**Question:** when many entities are visible, what part of the system starts becoming expensive?

Entities are interesting because they do not create a purely graphical workload. Minecraft also has to simulate them, update AI and animations, decide what is visible and prepare the corresponding rendering work.

This makes it useful to compare frame behavior with both Minecraft CPU usage and per-core CPU activity, while also looking at GPU utilization and GPU-active time per frame. The important part is to see whether the extra cost appears mainly before the GPU, during rendering, or across both sides at the same time.

## 3. Shaders OFF -> ON

**Question:** how does the system change when the rendering workload becomes significantly heavier?

This is one of the easiest experiments to control because the world itself can remain almost identical while the graphics workload changes. Enabling shaders may add more expensive shader programs, extra passes, shadow rendering and additional memory traffic.

Frame time, 1% low, GPU utilization, GPU-active time, clocks, power, temperature and VRAM are especially useful here because they show how the GPU reacts when the visual workload changes. If this experiment produces a clear graphics-side cost, it is also one of the most interesting cases to inspect later with PresentMon frame data and Nsight.

## 4. Render distance 8 -> 16 -> 32

**Question:** what actually scales when more of the world has to be kept visible?

Render distance is useful because it can be changed in clear steps while leaving most of the rest of the experiment unchanged. Increasing it can affect chunk processing, visible geometry, memory usage, disk activity and the amount of rendering work.

The interesting part is to line up each render-distance change with frame time, 1% low, VRAM, Minecraft CPU usage, per-core CPU activity, GPU activity and disk throughput. The exported render-distance value and annotations make it possible to see whether those resources scale gradually with the setting or react in a more irregular way.

## 5. Teleport / dimension transition

**Question:** what happens during a short but very visible stutter?

Teleportation and dimension changes are useful because several parts of Minecraft can change almost at once. New chunks may need to be loaded or generated, disk or network activity may appear, CPU work may spike and the rendering workload may change very quickly.

This is less about average performance and more about the exact moment where the stutter happens. Frame time and individual PresentMon samples are therefore particularly useful, alongside CPU activity, disk and network throughput, GPU utilization, GPU-active time, VRAM, clocks and power. The goal is to line up the hitch with the rest of the telemetry and see what changed during that short interval.


## Suggested experiment form

For each run, write down:

```text
Question
Hypothesis
Controlled scenario
Metrics selected before the run
Observed timeline
Conclusion
What evidence would falsify the conclusion?
```

## Useful experiment commands

### Shaders

```powershell
python tools\labctl.py start "Shaders test" --notes "same location; RD=16"
python tools\labctl.py event "Shaders OFF" --tags shader off
# play 30-60 s
python tools\labctl.py event "Shaders ON" --tags shader on
# play 30-60 s
python tools\labctl.py nsight "Shaders ON representative frame"
python tools\labctl.py stop
```

### Render distance

```powershell
python tools\labctl.py start "Render distance scaling"
python tools\labctl.py event "Render distance 8" --tags rd 8
python tools\labctl.py event "Render distance 16" --tags rd 16
python tools\labctl.py event "Render distance 32" --tags rd 32
python tools\labctl.py stop
```

### Teleport

```powershell
python tools\labctl.py start "Teleport stutter"
python tools\labctl.py event "Before teleport" --tags teleport before
# teleport immediately
python tools\labctl.py event "Teleport completed" --tags teleport after
python tools\labctl.py stop
```

