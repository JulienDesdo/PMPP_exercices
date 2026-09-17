# Metric interpretation cheatsheet

| Metric | Question it answers | It does **not** mean |
|---|---|---|
| `nvidia_gpu_utilization_percent` | During the driver's sampling window, how much time was GPU work active? | Percent of SMs physically occupied or percent of theoretical FLOPS used |
| `nvidia_gpu_graphics_clock_mhz` | How fast is the graphics clock currently running? | How busy the GPU is |
| `nvidia_gpu_pstate` | Which NVIDIA performance state is active? | A direct utilization percentage |
| `nvidia_gpu_power_draw_watts` | At what rate is the GPU consuming electrical energy now? | Total PC energy consumption |
| `nvidia_gpu_memory_used_bytes` | How much framebuffer memory is allocated/used? | How busy the memory subsystem is |
| `minecraft_frame_time_ms` | Time between application Presents | Exact time every internal Minecraft subsystem spent |
| `minecraft_frame_gpu_active_ms` | GPU active duration PresentMon attributes to a frame | A per-pipeline-stage breakdown |
| `system_cpu_core_utilization_percent` | Is one logical CPU becoming saturated? | Exact Minecraft main-thread time |

The useful skill is correlation: FPS/frametime tells you what the user felt; GPU/CPU/power/clocks tell you what the system was doing around the same timestamp.
