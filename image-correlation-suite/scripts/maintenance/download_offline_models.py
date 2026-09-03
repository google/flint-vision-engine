#!/usr/bin/env python3
# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""
SYMPICS Offline Model Provisioning & Air-Gap Bundler
=================================================
Pre-downloads AI vision and multimodal transformer weights from Hugging Face
into a self-contained local directory or transfer package for air-gapped forensic deployment.

Supported Models:
  • SigLIP Base        : google/siglip-base-patch16-224 (768-dim)
  • SigLIP-2 NaFlex    : google/siglip2-base-patch16-naflex (768-dim)
  • CLIP ViT-B/32      : openai/clip-vit-base-patch32 (512-dim)
  • DINOv3 ViT-B/16    : facebook/dinov3-vit-b-16 (768-dim vision-only)

Usage:
  python3 download_offline_models.py --target-dir ./models --models all
  python3 download_offline_models.py --target-dir ./models --models siglip,siglip2
  python3 download_offline_models.py --create-tar sympics-models-airgap.tar.gz
"""

import os
import sys
import argparse
import tarfile
import shutil

# Model Registry
MODEL_REGISTRY = {
    "siglip": {
        "name": "SigLIP Base",
        "repo_id": "google/siglip-base-patch16-224",
        "dimension": 768,
        "gated": False,
        "description": "Standard Google SigLIP ViT-B/16 text-image embedder"
    },
    "siglip2": {
        "name": "SigLIP-2 NaFlex",
        "repo_id": "google/siglip2-base-patch16-naflex",
        "dimension": 768,
        "gated": False,
        "description": "Native aspect ratio high-fidelity vision transformer"
    },
    "clip": {
        "name": "CLIP ViT-B/32",
        "repo_id": "openai/clip-vit-base-patch32",
        "dimension": 512,
        "gated": False,
        "description": "OpenAI multi-modal semantic search baseline"
    },
    "dinov3": {
        "name": "DINOv3 ViT-B/16",
        "repo_id": "facebook/dinov3-vit-b-16",
        "dimension": 768,
        "gated": True,
        "description": "Meta Self-Supervised Vision Transformer (Gated Access)"
    }
}


def download_model(key, info, target_dir, hf_token=None):
    print(f"\n===============================================================================")
    print(f"[*] Downloading {info['name']} ({info['repo_id']})")
    print(f"    Target Destination: {target_dir}")
    print(f"===============================================================================")

    model_subfolder = os.path.join(target_dir, key)
    os.makedirs(model_subfolder, exist_ok=True)

    token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("[!] Error: huggingface_hub is required. Install via: pip install huggingface_hub")
        sys.exit(1)

    try:
        snapshot_path = snapshot_download(
            repo_id=info["repo_id"],
            local_dir=model_subfolder,
            local_dir_use_symlinks=False,
            token=token
        )
        print(f"[+] Successfully downloaded {info['name']} to: {snapshot_path}")
        return True
    except Exception as e:
        print(f"[-] Failed to download {info['name']}: {e}")
        if info["gated"] and not token:
            print("    [!] Note: This is a gated model. Provide your HuggingFace token via --hf-token or HF_TOKEN env var.")
        return False


def create_tar_bundle(source_dir, output_tar):
    print(f"\n[*] Packaging offline model bundle into: {output_tar}...")
    with tarfile.open(output_tar, "w:gz") as tar:
        tar.add(source_dir, arcname="models")
    size_mb = os.path.getsize(output_tar) / (1024 * 1024)
    print(f"[+] Archive created successfully ({size_mb:.1f} MB).")


def main():
    parser = argparse.ArgumentParser(description="SYMPICS Offline AI Model Downloader & Provisioner")
    parser.add_argument("--target-dir", default="./models", help="Directory to store downloaded weights (default: ./models)")
    parser.add_argument("--models", default="all", help="Models to download: 'all', or comma-separated list: 'siglip,siglip2,clip,dinov3'")
    parser.add_argument("--hf-token", default=None, help="Hugging Face User Access Token (for gated models like DINOv3)")
    parser.add_argument("--create-tar", default=None, help="Optional: Package downloaded models into a compressed .tar.gz archive")
    parser.add_argument("--list", action="store_true", help="List all registered models and exit")

    args = parser.parse_args()

    if args.list:
        print("\nRegistered SYMPICS AI Vision Models:")
        print(f"{'Key':<10} {'Model Name':<20} {'Repo ID':<38} {'Dim':<6} {'Gated'}")
        print("-" * 80)
        for k, v in MODEL_REGISTRY.items():
            print(f"{k:<10} {v['name']:<20} {v['repo_id']:<38} {v['dimension']:<6} {str(v['gated']):<5}")
        return

    os.makedirs(args.target_dir, exist_ok=True)

    if args.models == "all":
        selected_keys = list(MODEL_REGISTRY.keys())
    else:
        selected_keys = [k.strip() for k in args.models.split(",") if k.strip() in MODEL_REGISTRY]

    if not selected_keys:
        print(f"[!] No valid models selected. Available keys: {list(MODEL_REGISTRY.keys())}")
        sys.exit(1)

    print(f"[*] Starting offline download for models: {', '.join(selected_keys)}")
    results = {}
    for key in selected_keys:
        info = MODEL_REGISTRY[key]
        success = download_model(key, info, args.target_dir, hf_token=args.hf_token)
        results[key] = success

    print("\n" + "=" * 60)
    print("DOWNLOAD SUMMARY")
    print("=" * 60)
    for k, ok in results.items():
        status = "COMPLETED" if ok else "FAILED"
        print(f"  • {MODEL_REGISTRY[k]['name']:<25}: {status}")

    if args.create_tar:
        create_tar_bundle(args.target_dir, args.create_tar)

    print("\n[*] Air-gap deployment instructions:")
    print(f"    1. Copy '{args.target_dir}' to your air-gapped server.")
    print("    2. Set SYMPICS_MODELS_DIR in your .env or place inside the project root under ./models/")
    print("    3. Launch SYMPICS. The multi-model engine will load directly from disk without internet access.")


if __name__ == "__main__":
    main()
