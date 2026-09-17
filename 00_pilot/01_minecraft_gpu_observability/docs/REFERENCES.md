# Implementation references

The lab design is based on the official documentation for:

- NVIDIA `nvidia-smi` / NVML GPU telemetry
- Prometheus scraping and Docker Desktop's `host.docker.internal`
- Grafana provisioning and Annotations HTTP API
- PresentMon command-line CSV output (`--process_id`, `--output_stdout`, `--v1_metrics`)
- NVIDIA Nsight Graphics OpenGL Frame Debugger / GPU Trace

Versions pinned in `docker-compose.yml` when this lab was generated:

- Prometheus 3.14.0
- Grafana 13.2.1
