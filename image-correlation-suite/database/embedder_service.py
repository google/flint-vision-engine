#!/usr/bin/env python3
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
===============================================================================
SYMPICS AI MULTI-MODEL EMBEDDER SERVICE
===============================================================================
Provides multi-model PyTorch feature vector extraction for:
  1. CLIP (ViT-B/32) -> 512-dimensional vector
  2. SigLIP (Base-patch16-224) -> 768-dimensional vector
  3. SigLIP-2 (NaFlex Base) -> 768-dimensional vector
Includes EXIF metadata parsing and fast WebP thumbnail generation.
===============================================================================
"""

import os
import sys
import numpy as np
from PIL import Image, ImageOps

from concurrent.futures import ThreadPoolExecutor

try:
    import torch
    from transformers import AutoProcessor, AutoModel, CLIPProcessor, CLIPModel
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


def _safe_load_model(model_cls, model_path, torch_dtype, device):
    """Loads model with PyTorch SDPA FlashAttention-2 acceleration when supported."""
    try:
        model = model_cls.from_pretrained(model_path, torch_dtype=torch_dtype, attn_implementation="sdpa").to(device)
        return model
    except Exception:
        # Fallback to standard attention
        model = model_cls.from_pretrained(model_path, torch_dtype=torch_dtype).to(device)
        return model


import io

CAMERA_RAW_EXTS = {".cr3", ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef", ".raf"}


def extract_embedded_raw_jpeg(raw_path):
    """
    Extracts the highest-resolution embedded JPEG preview from Canon CR3/CR2, Nikon NEF, Sony ARW, DNG, etc.
    Fast, memory-safe, and pure Python without requiring rawpy/libraw.
    """
    try:
        with open(raw_path, "rb") as f:
            data = f.read()

        idx = 0
        best_img = None
        best_pixel_count = 0

        while True:
            idx = data.find(b"\xff\xd8\xff", idx)
            if idx == -1:
                break
            eoi = data.find(b"\xff\xd9", idx)
            if eoi != -1:
                chunk = data[idx : eoi + 2]
                try:
                    im = Image.open(io.BytesIO(chunk))
                    w, h = im.size
                    if w * h > best_pixel_count:
                        best_pixel_count = w * h
                        best_img = ImageOps.exif_transpose(im).convert("RGB")
                except Exception:
                    pass
            idx += 3

        return best_img
    except Exception:
        return None


def load_image_or_raw(item):
    """
    Safely loads an image from path or PIL object. Supports standard images and Camera RAW files.
    """
    if isinstance(item, Image.Image):
        return item.convert("RGB")
    if not isinstance(item, str) or not os.path.exists(item):
        return None

    ext = os.path.splitext(item)[1].lower()
    if ext in CAMERA_RAW_EXTS:
        raw_img = extract_embedded_raw_jpeg(item)
        if raw_img is not None:
            return raw_img

    try:
        img = Image.open(item)
        return ImageOps.exif_transpose(img).convert("RGB")
    except Exception:
        # Fallback to embedded JPEG scan
        return extract_embedded_raw_jpeg(item)


def _resolve_model_path(model_id: str, aliases: list = None) -> str:
    """
    Resolves model location checking local ./models/ paths before falling back to HuggingFace.
    """
    local_roots = [
        os.environ.get("SYMPICS_MODELS_DIR", ""),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models"),
        os.path.join(os.getcwd(), "models"),
    ]
    candidates_names = [model_id, model_id.replace("/", "_"), model_id.split("/")[-1]]
    if aliases:
        candidates_names.extend(aliases)

    for root in local_roots:
        if not root or not os.path.isdir(root):
            continue
        for sub in candidates_names:
            candidate = os.path.join(root, sub)
            if os.path.isdir(candidate) and (os.path.exists(os.path.join(candidate, "config.json")) or os.path.exists(os.path.join(candidate, "model.safetensors"))):
                return candidate
    return model_id


class VisionEmbedderService:
    _instance = None

    def __init__(self, compute_options=None, device=None):
        if compute_options is None:
            self.compute_options = {"clip": True, "siglip": True, "siglip2_naflex": True, "dinov3": True}
        else:
            self.compute_options = compute_options

        if TORCH_AVAILABLE:
            self.device = device or ("cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu"))
            self.dtype = torch.float16 if self.device == "cuda" else torch.float32
            if self.device == "cpu" and hasattr(torch, "set_num_threads"):
                try:
                    torch.set_num_threads(min(12, os.cpu_count() or 4))
                except Exception:
                    pass
        else:
            self.device = "cpu"
            self.dtype = None

        self.clip_processor = None
        self.clip_model = None
        self.siglip_processor = None
        self.siglip_model = None
        self.siglip2_processor = None
        self.siglip2_model = None
        self.dinov3_processor = None
        self.dinov3_model = None

        self._load_models()

    def _load_models(self):
        if not TORCH_AVAILABLE:
            print("[!] PyTorch / Transformers not available. Using deterministic fallback.")
            return

        print(f"[*] Initializing Multi-Model AI Vision Engine on device: {self.device} (dtype: {self.dtype})...")

        # 1. CLIP (ViT-B/32, 512-dim)
        if self.compute_options.get("clip", True):
            try:
                clip_path = _resolve_model_path("openai/clip-vit-base-patch32", ["clip", "clip-vit-base-patch32"])
                print(f"    - Loading CLIP ({clip_path})...")
                self.clip_processor = CLIPProcessor.from_pretrained(clip_path)
                self.clip_model = _safe_load_model(CLIPModel, clip_path, self.dtype, self.device)
                self.clip_model.eval()
                print("      [+] CLIP loaded (512-dim).")
            except Exception as e:
                print(f"      [!] Warning: Could not load CLIP ({e}).")

        # 2. Standard SigLIP Base (768-dim)
        if self.compute_options.get("siglip", True):
            try:
                siglip_path = _resolve_model_path("google/siglip-base-patch16-224", ["siglip", "siglip-base-patch16-224"])
                print(f"    - Loading SigLIP Base ({siglip_path})...")
                self.siglip_processor = AutoProcessor.from_pretrained(siglip_path)
                self.siglip_model = _safe_load_model(AutoModel, siglip_path, self.dtype, self.device)
                self.siglip_model.eval()
                print("      [+] SigLIP Base loaded (768-dim).")
            except Exception as e:
                print(f"      [!] Warning: Could not load SigLIP Base ({e}).")

        # 3. SigLIP-2 NaFlex (768-dim)
        if self.compute_options.get("siglip2_naflex", True):
            try:
                siglip2_path = _resolve_model_path("google/siglip2-base-patch16-naflex", ["siglip2", "siglip2-base-patch16-naflex"])
                print(f"    - Loading SigLIP-2 NaFlex ({siglip2_path})...")
                self.siglip2_processor = AutoProcessor.from_pretrained(siglip2_path)
                self.siglip2_model = _safe_load_model(AutoModel, siglip2_path, self.dtype, self.device)
                self.siglip2_model.eval()
                print("      [+] SigLIP-2 NaFlex loaded (768-dim).")
            except Exception as e:
                print(f"      [!] Warning: Could not load SigLIP-2 NaFlex ({e}).")

        # 4. Meta DINOv3 (ViT-B/16, 768-dim)
        if self.compute_options.get("dinov3", True):
            try:
                dinov3_path = _resolve_model_path("facebook/dinov3-vitb16-pretrain-lvd1689m", ["dinov3", "dinov3-vitb16-pretrain-lvd1689m"])
                print(f"    - Loading DINOv3 ({dinov3_path})...")
                from transformers import AutoImageProcessor
                self.dinov3_processor = AutoImageProcessor.from_pretrained(dinov3_path)
                self.dinov3_model = _safe_load_model(AutoModel, dinov3_path, self.dtype, self.device)
                self.dinov3_model.eval()
                print("      [+] DINOv3 loaded (768-dim).")
            except Exception as e:
                print(f"      [!] Info: DINOv3 not available ({e}).")

    def _extract_model_features(self, model, processor, images, is_clip=False):
        if not images or model is None or processor is None:
            return []
        try:
            inputs = processor(images=images, return_tensors="pt").to(self.device)
            if self.dtype == torch.float16 and "pixel_values" in inputs:
                inputs["pixel_values"] = inputs["pixel_values"].to(self.dtype)

            inf_ctx = torch.inference_mode if hasattr(torch, "inference_mode") else torch.no_grad
            with inf_ctx():
                if hasattr(model, "get_image_features"):
                    output = model.get_image_features(**inputs)
                else:
                    output = model(**inputs)

                if isinstance(output, torch.Tensor):
                    features = output
                elif hasattr(output, "pooler_output") and output.pooler_output is not None:
                    features = output.pooler_output
                elif hasattr(output, "image_embeds") and output.image_embeds is not None:
                    features = output.image_embeds
                elif hasattr(output, "last_hidden_state") and output.last_hidden_state is not None:
                    features = output.last_hidden_state[:, 0, :]
                elif isinstance(output, (tuple, list)):
                    features = output[0]
                else:
                    features = output

                # L2 Normalize
                features = features / features.norm(dim=-1, keepdim=True)
                raw_np = features.cpu().numpy().astype(np.float32)
                return [raw_np[i].flatten().tolist() for i in range(len(images))]
        except Exception as e:
            print(f"[!] Feature extraction error: {e}")
            return []

    def compute_batch_embeddings(self, images_or_paths):
        """
        Computes dictionary of embeddings for a batch of images:
        Uses multi-threaded parallel CPU decoding across Threadripper cores.
        """
        if not images_or_paths:
            return []

        pil_images = []
        valid_indices = []

        # Parallel CPU image decoding
        max_workers = min(16, max(2, os.cpu_count() or 4))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            decoded = list(executor.map(load_image_or_raw, images_or_paths))

        for idx, img in enumerate(decoded):
            if img is not None:
                pil_images.append(img)
                valid_indices.append(idx)

        output = [{} for _ in range(len(images_or_paths))]
        if not pil_images:
            return output

        # 1. CLIP Batch
        clip_vecs = []
        if self.clip_model is not None and self.clip_processor is not None:
            clip_vecs = self._extract_model_features(self.clip_model, self.clip_processor, pil_images, is_clip=True)

        # 2. SigLIP Batch
        siglip_vecs = []
        if self.siglip_model is not None and self.siglip_processor is not None:
            siglip_vecs = self._extract_model_features(self.siglip_model, self.siglip_processor, pil_images, is_clip=False)

        # 3. SigLIP-2 NaFlex Batch
        siglip2_vecs = []
        if self.siglip2_model is not None and self.siglip2_processor is not None:
            siglip2_vecs = self._extract_model_features(self.siglip2_model, self.siglip2_processor, pil_images, is_clip=False)

        # 4. DINOv3 Batch
        dinov3_vecs = []
        if self.dinov3_model is not None and self.dinov3_processor is not None:
            dinov3_vecs = self._extract_model_features(self.dinov3_model, self.dinov3_processor, pil_images, is_clip=False)

        # Map back to original indices
        for i, orig_idx in enumerate(valid_indices):
            res = {}
            if i < len(clip_vecs) and clip_vecs[i]:
                res["clip"] = clip_vecs[i]
            if i < len(siglip_vecs) and siglip_vecs[i]:
                res["siglip"] = siglip_vecs[i]
            if i < len(siglip2_vecs) and siglip2_vecs[i]:
                res["siglip2_naflex"] = siglip2_vecs[i]
            if i < len(dinov3_vecs) and dinov3_vecs[i]:
                res["dinov3"] = dinov3_vecs[i]

            # Fallback if torch not loaded
            if not res:
                import hashlib
                h = hashlib.sha256(pil_images[i].tobytes()).digest()
                seed = int.from_bytes(h[:4], "big")
                np.random.seed(seed)

                v512 = np.random.randn(512).astype(np.float32)
                v512 /= np.linalg.norm(v512)
                res["clip"] = v512.tolist()

                v768 = np.random.randn(768).astype(np.float32)
                v768 /= np.linalg.norm(v768)
                res["siglip"] = v768.tolist()

                v768_2 = np.random.randn(768).astype(np.float32)
                v768_2 /= np.linalg.norm(v768_2)
                res["siglip2_naflex"] = v768_2.tolist()

                v768_3 = np.random.randn(768).astype(np.float32)
                v768_3 /= np.linalg.norm(v768_3)
                res["dinov3"] = v768_3.tolist()

            output[orig_idx] = res

        return output

    def compute_single_image_embedding(self, image_path_or_pil, model_name="siglip2_naflex"):
        """
        Computes vector embedding for a single image using ONLY the requested model.
        Significantly faster than compute_all_embeddings for interactive searches.
        """
        model_name = (model_name or "siglip2_naflex").lower()

        if isinstance(image_path_or_pil, str):
            from sympics.core.raw_extractor import load_image_or_raw
            img = load_image_or_raw(image_path_or_pil)
        else:
            img = image_path_or_pil

        if img is None:
            return None

        if img.mode != "RGB":
            img = img.convert("RGB")

        if not TORCH_AVAILABLE:
            return self.compute_all_embeddings(img).get(model_name)

        if model_name == "clip" and self.clip_model and self.clip_processor:
            feats = self._extract_model_features(self.clip_model, self.clip_processor, [img], is_clip=True)
            return feats[0] if feats else None
        elif model_name == "siglip" and self.siglip_model and self.siglip_processor:
            feats = self._extract_model_features(self.siglip_model, self.siglip_processor, [img], is_clip=False)
            return feats[0] if feats else None
        elif model_name == "siglip2_naflex" and self.siglip2_model and self.siglip2_processor:
            feats = self._extract_model_features(self.siglip2_model, self.siglip2_processor, [img], is_clip=False)
            return feats[0] if feats else None
        elif model_name == "dinov3" and self.dinov3_model and self.dinov3_processor:
            feats = self._extract_model_features(self.dinov3_model, self.dinov3_processor, [img], is_clip=False)
            return feats[0] if feats else None
        else:
            return self.compute_all_embeddings(img).get(model_name)

    def compute_all_embeddings(self, image_path_or_pil):
        """
        Computes dictionary of embeddings for a single image:
        Returns: {
            "clip": [float x 512],
            "siglip": [float x 768],
            "siglip2_naflex": [float x 768]
        }
        """
        batch_res = self.compute_batch_embeddings([image_path_or_pil])
        return batch_res[0] if batch_res else {}

    def compute_all_text_embeddings(self, text):
        """
        Computes text embeddings across all available models:
        Returns: {
            "clip": [float x 512],
            "siglip": [float x 768],
            "siglip2_naflex": [float x 768]
        }
        """
        if not text or not text.strip():
            return {}
        text = text.strip()
        results = {}

        if not TORCH_AVAILABLE:
            return results

        # 1. CLIP Text Features
        if self.clip_model is not None and self.clip_processor is not None:
            try:
                inputs = self.clip_processor(text=[text], return_tensors="pt", padding=True).to(self.device)
                inf_ctx = torch.inference_mode if hasattr(torch, "inference_mode") else torch.no_grad
                with inf_ctx():
                    tf = self.clip_model.get_text_features(**inputs)
                    if hasattr(tf, "text_embeds") and tf.text_embeds is not None:
                        tf = tf.text_embeds
                    elif hasattr(tf, "pooler_output") and tf.pooler_output is not None:
                        tf = tf.pooler_output
                    elif not isinstance(tf, torch.Tensor):
                        tf = tf[0]
                    tf = tf / tf.norm(dim=-1, keepdim=True)
                    results["clip"] = tf.cpu().numpy().astype(np.float32)[0].tolist()
            except Exception as e:
                print(f"[!] CLIP text embedding error: {e}")

        # 2. SigLIP Base Text Features
        if self.siglip_model is not None and self.siglip_processor is not None:
            try:
                inputs = self.siglip_processor(text=[text], return_tensors="pt", padding="max_length").to(self.device)
                inf_ctx = torch.inference_mode if hasattr(torch, "inference_mode") else torch.no_grad
                with inf_ctx():
                    tf = self.siglip_model.get_text_features(**inputs)
                    if hasattr(tf, "text_embeds") and tf.text_embeds is not None:
                        tf = tf.text_embeds
                    elif hasattr(tf, "pooler_output") and tf.pooler_output is not None:
                        tf = tf.pooler_output
                    elif not isinstance(tf, torch.Tensor):
                        tf = tf[0]
                    tf = tf / tf.norm(dim=-1, keepdim=True)
                    results["siglip"] = tf.cpu().numpy().astype(np.float32)[0].tolist()
            except Exception as e:
                print(f"[!] SigLIP text embedding error: {e}")

        # 3. SigLIP2 NaFlex Text Features
        if self.siglip2_model is not None and self.siglip2_processor is not None:
            try:
                inputs = self.siglip2_processor(text=[text], return_tensors="pt", padding="max_length").to(self.device)
                inf_ctx = torch.inference_mode if hasattr(torch, "inference_mode") else torch.no_grad
                with inf_ctx():
                    tf = self.siglip2_model.get_text_features(**inputs)
                    if hasattr(tf, "text_embeds") and tf.text_embeds is not None:
                        tf = tf.text_embeds
                    elif hasattr(tf, "pooler_output") and tf.pooler_output is not None:
                        tf = tf.pooler_output
                    elif not isinstance(tf, torch.Tensor):
                        tf = tf[0]
                    tf = tf / tf.norm(dim=-1, keepdim=True)
                    results["siglip2_naflex"] = tf.cpu().numpy().astype(np.float32)[0].tolist()
            except Exception as e:
                print(f"[!] SigLIP-2 text embedding error: {e}")

        return results

    def compute_text_embedding(self, text, model_name="siglip2_naflex"):
        """Computes text embedding vector for a specific model directly without running unused models."""
        if not text:
            return []
        
        m_lower = (model_name or "siglip2_naflex").lower()
        inf_ctx = torch.inference_mode if hasattr(torch, "inference_mode") else torch.no_grad

        # 1. CLIP (512-dim)
        if m_lower == "clip":
            if self.clip_model is not None and self.clip_processor is not None:
                try:
                    inputs = self.clip_processor(text=[text], return_tensors="pt", padding=True).to(self.device)
                    with inf_ctx():
                        tf = self.clip_model.get_text_features(**inputs)
                        if hasattr(tf, "text_embeds") and tf.text_embeds is not None:
                            tf = tf.text_embeds
                        elif hasattr(tf, "pooler_output") and tf.pooler_output is not None:
                            tf = tf.pooler_output
                        elif not isinstance(tf, torch.Tensor):
                            tf = tf[0]
                        tf = tf / tf.norm(dim=-1, keepdim=True)
                        return tf.cpu().numpy().astype(np.float32)[0].tolist()
                except Exception as e:
                    print(f"[!] CLIP text embedding error: {e}")
            return []

        # 2. SigLIP Base (768-dim)
        elif m_lower == "siglip":
            if self.siglip_model is not None and self.siglip_processor is not None:
                try:
                    inputs = self.siglip_processor(text=[text], return_tensors="pt", padding="max_length").to(self.device)
                    with inf_ctx():
                        tf = self.siglip_model.get_text_features(**inputs)
                        if hasattr(tf, "text_embeds") and tf.text_embeds is not None:
                            tf = tf.text_embeds
                        elif hasattr(tf, "pooler_output") and tf.pooler_output is not None:
                            tf = tf.pooler_output
                        elif not isinstance(tf, torch.Tensor):
                            tf = tf[0]
                        tf = tf / tf.norm(dim=-1, keepdim=True)
                        return tf.cpu().numpy().astype(np.float32)[0].tolist()
                except Exception as e:
                    print(f"[!] SigLIP text embedding error: {e}")
            return []

        # 3. SigLIP-2 NaFlex (768-dim, Default)
        else:
            if self.siglip2_model is not None and self.siglip2_processor is not None:
                try:
                    inputs = self.siglip2_processor(text=[text], return_tensors="pt", padding="max_length").to(self.device)
                    with inf_ctx():
                        tf = self.siglip2_model.get_text_features(**inputs)
                        if hasattr(tf, "text_embeds") and tf.text_embeds is not None:
                            tf = tf.text_embeds
                        elif hasattr(tf, "pooler_output") and tf.pooler_output is not None:
                            tf = tf.pooler_output
                        elif not isinstance(tf, torch.Tensor):
                            tf = tf[0]
                        tf = tf / tf.norm(dim=-1, keepdim=True)
                        return tf.cpu().numpy().astype(np.float32)[0].tolist()
                except Exception as e:
                    print(f"[!] SigLIP-2 text embedding error: {e}")
            return []

    def compute_embedding(self, image_path_or_pil, model_name="siglip"):
        """Backward-compatible single-model embedding query."""
        all_embs = self.compute_all_embeddings(image_path_or_pil)
        return all_embs.get(model_name) or all_embs.get("siglip")

    @staticmethod
    def generate_thumbnail(source_image_path, dest_thumb_path, max_dim=256):
        """
        Generates a 256px WebP thumbnail and returns (width, height, exif_json).
        Supports standard images and Camera RAW files (CR3, CR2, NEF, ARW, DNG, etc.).
        """
        try:
            os.makedirs(os.path.dirname(dest_thumb_path), exist_ok=True)
            img = load_image_or_raw(source_image_path)
            if img is None:
                return None, None, {}

            w, h = img.size

            exif_dict = {}
            try:
                exif_data = img.getexif() if hasattr(img, "getexif") else None
                if exif_data:
                    from PIL.ExifTags import TAGS
                    for tag_id, val in exif_data.items():
                        tag_name = TAGS.get(tag_id, str(tag_id))
                        if tag_name in ("Make", "Model", "DateTime", "DateTimeOriginal", "Software"):
                            exif_dict[tag_name] = str(val).strip()
            except Exception:
                pass

            thumb = img.copy()
            thumb.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            thumb.convert("RGB").save(dest_thumb_path, format="WEBP", quality=85)

            return w, h, exif_dict
        except Exception as e:
            print(f"[!] Thumbnail generation error for {source_image_path}: {e}")
            return None, None, {}


_global_embedder = None

def get_embedder():
    global _global_embedder
    if _global_embedder is None:
        _global_embedder = VisionEmbedderService()
    return _global_embedder

