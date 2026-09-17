# PMPP Exercices 

`PMPP_exercises` is a repository containing several exercises based on reworked chapters from the *Programming Massively Parallel Processors* book.

As AI keeps growing faster, infrastructure management — especially around GPUs — is becoming an increasingly important stake. I personally reckon that it is useful to develop practical projects to learn single-GPU management before tackling the DevOps side of GPU infrastructure.

This is why this repo exists.

## Repository structure

The repository is organized by chapter, with a preliminary `00_pilot` section for GPU observability and system-level exercises that come before the book's CUDA-focused chapters.

```text
00_pilot/
01_chapter_01/
02_chapter_02/
...
```

Current pilot project: [`00_pilot/01_minecraft_gpu_observability`](00_pilot/01_minecraft_gpu_observability)