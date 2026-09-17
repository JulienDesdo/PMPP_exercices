# Troubleshooting

Most problems in this lab come from one of three boundaries:

```text
Docker
    <->
Windows exporter
    <->
PresentMon / Minecraft
```

When something is missing from Grafana, it is usually easier to check those layers separately than to restart everything blindly.

## Docker is not running

Prometheus and Grafana require Docker Desktop to be running.

Check:

```powershell
docker info
```

If Docker cannot reach its daemon, start Docker Desktop and wait until it is ready before launching the lab again.

## Check the exporter directly

The Windows exporter exposes its current Prometheus metrics on:

```text
http://localhost:9835/metrics
```

From PowerShell:

```powershell
Invoke-WebRequest http://localhost:9835/metrics |
    Select-Object -Expand Content
```

Useful health signals include:

```text
gpu_lab_exporter_up 1
nvidia_smi_up{gpu="0"} 1
minecraft_process_up 1
minecraft_presentmon_up 1
```

They help separate different failures.

For example, Minecraft metrics may work while `minecraft_presentmon_up` remains `0`, which points toward the PresentMon side rather than Prometheus or Grafana.

## PresentMon permissions

PresentMon needs permission to create an ETW tracing session.

Without the required permissions it may start as a process but fail with an error similar to:

```text
failed to start trace session: access denied
```

Running the lab from an Administrator PowerShell avoids this during development.

A permanent alternative is to add the Windows account to the **Performance Log Users** group.

After changing group membership, sign out and sign back in before testing again.

## PresentMon is running but no frame data arrives

A healthy exporter eventually prints:

```text
[presentmon] attached to PID ...
[presentmon] CSV stream started
```

`minecraft_presentmon_up 1` means that the exporter has actually received the PresentMon CSV stream. The presence of a `PresentMon.exe` process alone is not enough.

If PresentMon does not reach the CSV stage, run it directly against the Minecraft PID to separate PresentMon itself from the exporter:

```powershell
C:\Tools\PresentMon\PresentMon.exe `
    --process_id <PID> `
    --output_stdout `
    --v1_metrics `
    --no_console_stats
```

A working capture should continuously print CSV rows while Minecraft renders frames.

## Stale PresentMon or ETW session

During development it is possible to leave a PresentMon process or trace session behind, especially after repeated manual captures or an unclean shutdown.

Check for remaining PresentMon processes:

```powershell
Get-Process PresentMon -ErrorAction SilentlyContinue
```

If one should no longer be running:

```powershell
Stop-Process -Name PresentMon -Force
```

The exporter uses a dedicated ETW session name based on the Minecraft PID:

```text
MinecraftGpuLab_<PID>
```

PresentMon may warn on the next start that an existing session with that name is being stopped. This usually means a previous capture did not clean up normally.

During development, repeated manual PresentMon runs, forced process termination and stale ETW state once resulted in large numbers of lost trace events and no CSV output even when PresentMon was launched independently.

Restarting Windows reset the tracing environment and restored normal capture.

That does not prove exactly which internal ETW state had become invalid, but it is a useful last resort once the normal process/session cleanup has been checked.

## Stop the exporter cleanly

Use:

```text
Ctrl+C
```

before closing the exporter terminal.

The exporter owns the PresentMon subprocess and should terminate it when the lab stops.

Killing the terminal or Python process abruptly can bypass normal cleanup and leave PresentMon or its ETW tracing session behind.

## Prometheus and Grafana are running but show no data

Check the chain in order:

```text
http://localhost:9835/metrics
        |
        v
Prometheus target
        |
        v
Grafana datasource/dashboard
```

If `/metrics` already contains the expected values, the exporter is working and the problem is further downstream.

If the endpoint itself is missing the value, Prometheus and Grafana cannot recover it: investigate the exporter or collector responsible for that metric first.