# Processing Benchmarks
Processing massive datasets natively requires understanding hardware capabilities. Below are estimated processing times for computing **1 TB of images** (assuming each image is 500 KB, totaling **2,000,000 images**) across different models and hardware configurations. Times account for image loading, preprocessing, and model inference.
| Model | Intel Core Ultra 5 (CPU) | Apple M5 (CPU / Neural Engine) | NVIDIA RTX 3060 (GPU - Batched) |
| :--- | :--- | :--- | :--- |
| **mobileCLIP** | ~8 hours (*~15 ms/img*) | ~5.5 hours (*~10 ms/img*) | ~1.1 hours (*~2 ms/img*) |
| **CLIP ViT-B/32** | ~17 hours (*~30 ms/img*) | ~8.5 hours (*~15 ms/img*) | ~1.6 hours (*~3 ms/img*) |
| **CLIP ViT-B/14** | ~28 hours (*~50 ms/img*) | ~14 hours (*~25 ms/img*) | ~3 hours (*~5 ms/img*) |
| **SigLIP2 Base** | ~25 hours (*~45 ms/img*) | ~11 hours (*~20 ms/img*) | ~2.2 hours (*~4 ms/img*) |
| **SigLIP2 NaFlex** | ~42 hours (*~75 ms/img*) | ~22 hours (*~40 ms/img*) | ~5.5 hours (*~10 ms/img*) |
| **DINOv3 ViT-B/16** | ~33 hours (*~60 ms/img*) | ~19 hours (*~35 ms/img*) | ~4.5 hours (*~8 ms/img*) |
---
### Hardware Takeaways
1. **Edge/Laptops**: `mobileCLIP` and `SigLIP2 Base` offer exceptional throughput on standard forensic investigator laptops (Apple M-series or modern Intel CPUs).
2. **Dedicated Triage Stations**: Moderate GPUs (such as RTX 3060) process multi-million image databases in under 2–3 hours.
