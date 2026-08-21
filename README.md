# FLINT Vision Engine

The **FLINT Vision Engine** is an open-source, edge-native framework designed to let you plug in any vision-language or vision-only foundational model to conduct advanced image and video triage.

While the system is model-agnostic, we recommend the following models based on their distinct architectural characteristics:

- **mobileCLIP**: Lightweight and fast, ideal for low-power edge devices.
- **CLIP ViT-B/32**: Highly efficient baseline model offering a great balance of speed and semantic matching accuracy.
- **CLIP ViT-B/14**: Suited for zero-shot classification and semantic matching with finer patch details.
- **SigLIP2 Base**: Standard SigLIP2 variant offering strong baseline performance for global image features.
- **SigLIP2 NaFlex**: Retains native aspect ratios and spatial details, suitable for crop-searching and intricate details.
- **DINOv3 ViT-B/16**: A vision-only model that focuses on structural and pixel-level feature matching (*Note: does not support text-to-image search*).

---

## Core Functionalities

- **Zero-Shot Visual Similarity Search**: Instantly discover images and video keyframes that are visually or semantically similar to a known reference image (or a seed set of images), completely bypassing the overhead of training or deploying custom classifiers.
- **Semantic Text-to-Image Search**: Query massive, unindexed media repositories using natural language text descriptions to accurately surface matching images without relying on metadata or manual tags.
- **Targeted Crop Searching**: Draw a bounding box to isolate a specific object, pattern, or region of interest within an image, and rapidly search your entire media database to locate other files containing that specific visual element.

---

## 1. Dependencies and Downloads

> **IMPORTANT**: To ensure compliance with licensing and Terms of Service (ToS) of various AI model providers, this repository **does not automatically download models from the internet at runtime**. All models and libraries must be manually downloaded and stored locally.

### Required Libraries
Install the following libraries in your offline or secure environment. You may download the `.whl` files via `pip download` on a connected machine and transfer them:
```bash
pip install torch torchvision transformers pillow opencv-python numpy pymysql psycopg2-binary
