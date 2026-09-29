# Supported Models & Offline Download Guide

To ensure compliance with licensing and Terms of Service (ToS) of various AI model providers, this repository **does not automatically download models from the internet at runtime**. All models and weights must be manually downloaded prior to execution in air-gapped or offline environments.

---

### Model Architecture Comparison

| Model | Modality | Primary Strengths | Recommended Comparison Metric |
| :--- | :--- | :--- | :--- |
| **mobileCLIP** | Vision + Text | Ultra-lightweight & fast; optimized for low-power edge/laptop deployments. | Cosine Similarity (L2 Normalized) |
| **CLIP ViT-B/32** | Vision + Text | Efficient baseline; strong balance of speed and zero-shot retrieval accuracy. | Cosine Similarity (L2 Normalized) |
| **CLIP ViT-B/14** | Vision + Text | High-resolution patch details; excellent fine-grained semantic classification. | Cosine Similarity (L2 Normalized) |
| **SigLIP2 Base** | Vision + Text | Trained with pairwise sigmoid loss; strong global image representation. | Cosine Similarity (L2 Normalized) |
| **SigLIP2 NaFlex** | Vision + Text | Retains native aspect ratios & spatial dimensions without squashing crops. | **Dot Product** (Raw Magnitudes) |
| **DINOv3 ViT-B/16** | Vision-Only | Captures minute pixel-level textures and structural patterns (*no text queries*). | Cosine Similarity or **L2 Distance** |

---

### Model Download Commands

Run these commands in a connected environment using the `huggingface-cli` to download the weights locally:

```bash
# 1. mobileCLIP
huggingface-cli download apple/mobileclip_s0 --local-dir ./models/mobileclip

# 2. CLIP ViT-B/32
huggingface-cli download openai/clip-vit-base-patch32 --local-dir ./models/clip-vit-b-32

# 3. CLIP ViT-B/14
huggingface-cli download openai/clip-vit-base-patch14 --local-dir ./models/clip-vit-b-14

# 4. SigLIP2 Base
huggingface-cli download google/siglip2-base-patch16-224 --local-dir ./models/siglip2-base

# 5. SigLIP2 NaFlex
huggingface-cli download google/siglip2-base-patch16-naflex --local-dir ./models/siglip2-naflex

# 6. DINOv3 ViT-B/16
huggingface-cli download facebook/dinov3-vitb16-pretrain-lvd1689m --local-dir ./models/dinov3-vitb16-pretrain-lvd1689m
