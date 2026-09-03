#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
===============================================================================
SYMPICS HARDWARE DISCOVERY & CONCURRENCY AUTO-TUNING ENGINE
===============================================================================
Automatically inspects the host environment (NVIDIA CUDA, Apple MPS, or CPU),
queries GPU VRAM, physical/logical CPU cores, and system memory, and calculates
optimal worker counts, batch sizes, and PyTorch precision settings.
===============================================================================
"""

import os
import sys
import platform
from dataclasses import dataclass
from typing import Optional

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


@dataclass
class HardwareProfile:
    device: str                   # "cuda", "mps", "cpu"
    device_name: str              # e.g. "NVIDIA GeForce RTX 4090", "Intel(R) Xeon(R)"
    gpu_count: int                # Number of available GPUs
    vram_gb: float                # Total VRAM of primary GPU (0.0 if CPU)
    cpu_cores: int                # Total CPU cores available
    ram_gb: float                 # System RAM in GB
    recommended_workers: int      # Optimal number of parallel worker processes
    recommended_batch_size: int   # Optimal batch size per worker
    recommended_dtype: str        # "float16", "bfloat16", "float32"

    def to_dict(self):
        return {
            "device": self.device,
            "device_name": self.device_name,
            "gpu_count": self.gpu_count,
            "vram_gb": round(self.vram_gb, 2),
            "cpu_cores": self.cpu_cores,
            "ram_gb": round(self.ram_gb, 2),
            "recommended_workers": self.recommended_workers,
            "recommended_batch_size": self.recommended_batch_size,
            "recommended_dtype": self.recommended_dtype,
        }


def _get_system_ram_gb() -> float:
    """Gets total system RAM in GB safely across Linux, macOS, and Windows."""
    try:
        if sys.platform == "linux" and os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb / (1024 * 1024)
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 16.0  # Safe default assumption


def _get_cpu_name() -> str:
    """Returns human-readable CPU brand string."""
    try:
        if sys.platform == "linux" and os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo", "r") as f:
                for line in f:
                    if "model name" in line:
                        return line.split(":", 1)[1].strip()
        return platform.processor() or "Generic CPU"
    except Exception:
        return "Generic CPU"


def probe_hardware() -> HardwareProfile:
    """
    Probes system hardware and returns an auto-tuned HardwareProfile.
    """
    cpu_cores = os.cpu_count() or 4
    try:
        cpu_cores = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        pass

    ram_gb = _get_system_ram_gb()
    cpu_name = _get_cpu_name()

    # 1. Check for NVIDIA CUDA GPU
    if TORCH_AVAILABLE and torch.cuda.is_available():
        gpu_count = torch.cuda.device_count()
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / (1024 ** 3)
        device_name = props.name

        # CUDA Concurrency Calculation:
        # Each worker consumes ~2.5 to 3.5 GB VRAM for CLIP + SigLIP + SigLIP-2
        workers = max(1, min(int(vram_gb / 3.5), 6))
        batch_size = 32 if vram_gb >= 16.0 else 16
        dtype = "float16"

        return HardwareProfile(
            device="cuda",
            device_name=f"{device_name} (x{gpu_count})" if gpu_count > 1 else device_name,
            gpu_count=gpu_count,
            vram_gb=vram_gb,
            cpu_cores=cpu_cores,
            ram_gb=ram_gb,
            recommended_workers=workers,
            recommended_batch_size=batch_size,
            recommended_dtype=dtype
        )

    # 2. Check for Apple Silicon MPS
    if TORCH_AVAILABLE and hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        workers = max(1, min(int(ram_gb / 8.0), 3))
        batch_size = 16
        dtype = "float32"

        return HardwareProfile(
            device="mps",
            device_name=f"Apple Silicon GPU (MPS / {cpu_name})",
            gpu_count=1,
            vram_gb=ram_gb * 0.7,  # Unified memory
            cpu_cores=cpu_cores,
            ram_gb=ram_gb,
            recommended_workers=workers,
            recommended_batch_size=batch_size,
            recommended_dtype=dtype
        )

    # 3. CPU Mode
    # Each CPU worker uses ~2.5 GB RAM and 3-4 CPU threads.
    # Sweet spot on CPU is cores / 3, capped at 8 to prevent thread contention.
    workers = max(1, min(int(cpu_cores / 3), int(ram_gb / 2.5), 8))
    batch_size = 16
    dtype = "float32"

    return HardwareProfile(
        device="cpu",
        device_name=cpu_name,
        gpu_count=0,
        vram_gb=0.0,
        cpu_cores=cpu_cores,
        ram_gb=ram_gb,
        recommended_workers=workers,
        recommended_batch_size=batch_size,
        recommended_dtype=dtype
    )


def print_hardware_banner(profile: Optional[HardwareProfile] = None):
    """Prints a styled terminal summary of the detected hardware."""
    p = profile or probe_hardware()
    print("===============================================================================")
    print("  SYMPICS HARDWARE PROBE & AUTO-TUNING")
    print("===============================================================================")
    print(f"  • Execution Device   : {p.device.upper()} ({p.device_name})")
    if p.device == "cuda":
        print(f"  • GPU VRAM           : {p.vram_gb:.1f} GB ({p.gpu_count} GPU{'s' if p.gpu_count > 1 else ''})")
    print(f"  • System CPU / RAM   : {p.cpu_cores} Cores | {p.ram_gb:.1f} GB RAM")
    print(f"  • Precision Model    : {p.recommended_dtype.upper()}")
    print(f"  • Auto-Tuned Workers : {p.recommended_workers} Parallel Processes")
    print(f"  • Batch Size/Worker  : {p.recommended_batch_size} Items / Batch")
    print("===============================================================================\n")


if __name__ == "__main__":
    prof = probe_hardware()
    print_hardware_banner(prof)
