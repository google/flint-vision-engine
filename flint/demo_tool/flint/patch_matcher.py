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

# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""DINOv3 Dense Spatial Patch Matcher & Object Localization Engine.

Provides fine-grained sub-object localization, Max-Cosine Chamfer patch alignment,
and spatial activation heatmap generation for cropped vision queries.
"""

import base64
import io
import os
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import cv2
import numpy as np
from PIL import Image, ImageOps
import torch
import torch.nn.functional as F


def extract_dense_patch_tokens(
    engine: Any,
    image_input: Union[str, Image.Image],
    crop_box: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
  """Extracts L2-normalized dense spatial patch tokens from DINOv3, SigLIP2 NaFlex, or CLIP ViT models."""
  if isinstance(image_input, str):
    ext = os.path.splitext(image_input)[1].lower()
    if ext in ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'):
      cap = cv2.VideoCapture(image_input)
      ret, frame = cap.read()
      cap.release()
      if ret and frame is not None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
      else:
        img = Image.new("RGB", (224, 224), (0, 0, 0))
    else:
      with Image.open(image_input) as raw_img:
        img = ImageOps.exif_transpose(raw_img).convert("RGB")
  else:
    img = ImageOps.exif_transpose(image_input).convert("RGB")

  w, h = img.size
  if crop_box:
    is_normalized = max(float(c) for c in crop_box) <= 1.05
    if is_normalized:
      x1, y1, x2, y2 = [max(0.0, min(1.0, float(c))) for c in crop_box]
      c_left = int(x1 * w)
      c_top = int(y1 * h)
      c_right = int(x2 * w)
      c_bottom = int(y2 * h)
    else:
      c_left, c_top, c_right, c_bottom = [int(float(c)) for c in crop_box]

    c_left = max(0, min(c_left, w - 8))
    c_top = max(0, min(c_top, h - 8))
    c_right = max(c_left + 8, min(c_right, w))
    c_bottom = max(c_top + 8, min(c_bottom, h))
    img = img.crop((c_left, c_top, c_right, c_bottom))

  inputs = engine.processor(images=[img], return_tensors="pt").to(engine.device)
  with torch.no_grad():
    m_name = getattr(engine, 'model_name', '').lower()
    if 'siglip2' in m_name and hasattr(engine.model, 'vision_model'):
      v_out = engine.model.vision_model(
          pixel_values=inputs.get("pixel_values"),
          attention_mask=inputs.get("pixel_attention_mask"),
          spatial_shapes=inputs.get("spatial_shapes"),
      )
      lhs = v_out.last_hidden_state  # [1, N_patches, 768]
      spatial_patches = lhs.squeeze(0)
      sp_shapes = inputs.get("spatial_shapes")
      if sp_shapes is not None and len(sp_shapes) > 0:
        h_p, w_p = int(sp_shapes[0][0].item()), int(sp_shapes[0][1].item())
        grid_size = (h_p, w_p)
      else:
        grid_size = int(np.sqrt(spatial_patches.shape[0]))
      normed_patches = F.normalize(spatial_patches, p=2, dim=-1)
      normed_cls = normed_patches.mean(dim=0)
      num_patches = spatial_patches.shape[0]

    elif 'clip' in m_name and hasattr(engine.model, 'vision_model'):
      v_out = engine.model.vision_model(pixel_values=inputs.get("pixel_values"))
      lhs = v_out.last_hidden_state  # [1, 50, 768] (1 CLS + 49 patches)
      cls_token = lhs[:, 0, :]
      spatial_patches = lhs[:, 1:, :]  # [1, 49, 768] (7x7 grid)
      if hasattr(engine.model, 'visual_projection'):
        spatial_patches = engine.model.visual_projection(spatial_patches)
        cls_token = engine.model.visual_projection(cls_token)
      normed_patches = F.normalize(spatial_patches, p=2, dim=-1).squeeze(0)
      normed_cls = F.normalize(cls_token, p=2, dim=-1).squeeze(0)
      grid_size = 7
      num_patches = 49

    else:
      # DINOv3 or standard ViT
      outputs = engine.model(**inputs)
      lhs = outputs.last_hidden_state  # [1, 201, 768]
      num_patches = 196 if lhs.shape[1] >= 196 else lhs.shape[1] - 1
      spatial_patches = lhs[:, -num_patches:, :]  # [1, 196, 768]
      normed_patches = F.normalize(spatial_patches, p=2, dim=-1).squeeze(0)
      cls_token = lhs[:, 0, :]
      normed_cls = F.normalize(cls_token, p=2, dim=-1).squeeze(0)
      grid_size = 14

  return {
      'spatial_patches': normed_patches,
      'cls_token': normed_cls,
      'grid_size': grid_size,
      'num_patches': num_patches,
      'hidden_dim': normed_patches.shape[-1],
      'img_size': img.size,
  }

def compute_patch_chamfer_alignment(
    q_patches: torch.Tensor,
    k_patches: torch.Tensor,
    grid_size: int = 14,
) -> Dict[str, Any]:
  """Computes Max-Cosine Chamfer patch alignment and generates high-precision spatial density activation."""
  device = q_patches.device
  # Similarity matrix S = Q * K^T -> [N_q, N_k]
  sim_matrix = torch.mm(q_patches, k_patches.t())

  # For every query crop patch, find max similarity and best candidate patch index
  max_sim_per_q, best_k_idx = sim_matrix.max(dim=1)
  chamfer_score = float(max_sim_per_q.mean().item())

  # Accumulate spatial activations on the candidate's grid_size x grid_size grid
  heatmap_1d = torch.zeros(grid_size * grid_size, device=device)
  for q_idx in range(q_patches.shape[0]):
    k_idx = int(best_k_idx[q_idx].item())
    if k_idx < len(heatmap_1d):
      heatmap_1d[k_idx] += max_sim_per_q[q_idx]

  heatmap_2d = heatmap_1d.view(grid_size, grid_size).cpu().numpy()
  h_min, h_max = heatmap_2d.min(), heatmap_2d.max()
  heatmap_norm = (heatmap_2d - h_min) / (h_max - h_min + 1e-8)

  # High-precision spatial clustering:
  # 1. Apply Gaussian spatial smoothing to merge contiguous patch activations and eliminate isolated noise
  smoothed = cv2.GaussianBlur(heatmap_2d, (3, 3), 0.75)
  peak_energy = float(smoothed.max())
  mean_energy = float(smoothed.mean())
  std_energy = float(smoothed.std())

  # 2. Adaptive thresholding for peak activation cluster
  thresh = max(0.48 * peak_energy, mean_energy + 0.6 * std_energy)
  binary = (smoothed >= thresh).astype(np.uint8)

  num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
  if num_labels > 1:
    # Select connected component with maximum cumulative alignment energy
    best_label = 1
    best_energy = -1.0
    for l in range(1, num_labels):
      comp_energy = float(heatmap_2d[labels == l].sum())
      if comp_energy > best_energy:
        best_energy = comp_energy
        best_label = l

    y_indices, x_indices = np.where(labels == best_label)
    x1 = round(max(0.0, float(x_indices.min()) / float(grid_size)), 3)
    y1 = round(max(0.0, float(y_indices.min()) / float(grid_size)), 3)
    x2 = round(min(1.0, float(x_indices.max() + 1) / float(grid_size)), 3)
    y2 = round(min(1.0, float(y_indices.max() + 1) / float(grid_size)), 3)
    localized_box = [x1, y1, x2, y2]
  else:
    # Fallback to energy quantile
    y_indices, x_indices = np.where(heatmap_norm >= 0.55)
    if len(y_indices) > 0:
      x1 = round(max(0.0, float(x_indices.min()) / float(grid_size)), 3)
      y1 = round(max(0.0, float(y_indices.min()) / float(grid_size)), 3)
      x2 = round(min(1.0, float(x_indices.max() + 1) / float(grid_size)), 3)
      y2 = round(min(1.0, float(y_indices.max() + 1) / float(grid_size)), 3)
      localized_box = [x1, y1, x2, y2]
    else:
      localized_box = [0.25, 0.25, 0.75, 0.75]

  # Compute max patch score
  max_patch_score = round(float(sim_matrix.max().item()) * 100.0, 2)
  chamfer_pct = round(chamfer_score * 100.0, 2)

  return {
      'chamfer_score': chamfer_score,
      'chamfer_similarity_pct': chamfer_pct,
      'max_patch_score': max_patch_score,
      'localized_box': localized_box,
      'heatmap_2d': heatmap_2d,
      'heatmap_norm': heatmap_norm,
      'grid_size': grid_size,
  }

def generate_patch_heatmap_data_url(
    heatmap_norm: Any,
    candidate_img_path: str,
    localized_box: Sequence[float],
) -> str:
  """Renders a thermal activation overlay on the candidate image and returns a base64 Data URL."""
  if not os.path.exists(candidate_img_path):
    return ""

  try:
    with Image.open(candidate_img_path) as raw_img:
      img = ImageOps.exif_transpose(raw_img).convert("RGB")
    w, h = img.size

    # Resize heatmap to image dimensions
    heatmap_np = np.array(heatmap_norm, dtype=np.float32)
    heatmap_img = cv2.resize(heatmap_np, (w, h), interpolation=cv2.INTER_CUBIC)
    heatmap_uint8 = np.uint8(255 * np.clip(heatmap_img, 0, 1))
    
    # Apply JET colormap
    color_heatmap = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
    color_heatmap = cv2.cvtColor(color_heatmap, cv2.COLOR_BGR2RGB)

    # Blend with original image (40% heatmap + 60% original)
    img_np = np.array(img)
    blended = cv2.addWeighted(img_np, 0.60, color_heatmap, 0.40, 0)

    # Draw localized bounding box on the blended image
    bx1, by1, bx2, by2 = localized_box
    pt1 = (int(bx1 * w), int(by1 * h))
    pt2 = (int(bx2 * w), int(by2 * h))
    cv2.rectangle(blended, pt1, pt2, (0, 242, 254), 3)

    out_pil = Image.fromarray(blended)
    out_pil.thumbnail((720, 720))
    buf = io.BytesIO()
    out_pil.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"
  except Exception:
    return ""


def build_patch_matching_forensic_explanation(
    crop_info: Dict[str, Any],
    patch_diagnostics: Dict[str, Any],
    global_score_pct: float,
) -> Dict[str, Any]:
  """Constructs educational forensic documentation and step-by-step explanation for the UI."""
  chamfer_pct = patch_diagnostics.get('chamfer_similarity_pct', 0.0)
  bbox = patch_diagnostics.get('localized_box', [0, 0, 1, 1])
  q_patches = patch_diagnostics.get('num_query_patches', 196)

  return {
      'title': 'DINOv3 Dense Spatial Patch Alignment',
      'rationale': (
          'Cropped visual queries contain isolated sub-objects that are easily diluted by surrounding background '
          'clutter when using standard global [CLS] pooling. DINOv3 bypasses global pooling by extracting all '
          f'{q_patches} self-supervised spatial patch embeddings, cross-aligning each localized patch across the '
          'candidate image to achieve invariant object detection and precise bounding-box localization.'
      ),
      'pipeline_steps': [
          {
              'step': 1,
              'name': 'Dense Patch Decomposition',
              'description': f'Extracted {q_patches} individual 768-dimensional spatial patch vectors from the cropped query region.',
              'metric': f'{q_patches} Spatial Tokens (14x14 Grid)',
          },
          {
              'step': 2,
              'name': 'Max-Cosine Chamfer Cross-Matching',
              'description': 'Cross-multiplied query patch matrix Q against candidate patch grid K; mapped each query patch to its maximal spatial counterpart.',
              'metric': f'{chamfer_pct}% Mean-Max Alignment Score',
          },
          {
              'step': 3,
              'name': 'Spatial Activation Density',
              'description': 'Projected the patch similarity energy onto the candidate 2D manifold to isolate high-density target clusters.',
              'metric': f'Peak Patch Alignment: {patch_diagnostics.get("max_patch_score", 0)}%',
          },
          {
              'step': 4,
              'name': 'Automated Bounding Box Localization',
              'description': 'Synthesized spatial activation cluster into a localized candidate bounding box.',
              'metric': f'Predicted Box: [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]',
          },
      ],
      'comparison': {
          'global_cls_score': f'{round(global_score_pct, 1)}%',
          'dense_patch_score': f'{chamfer_pct}%',
          'confidence_gain': f'+{round(max(0, chamfer_pct - global_score_pct), 1)}%',
          'localized_box': bbox,
      },
  }


def compute_text_patch_localization(
    text_vector: Sequence[float],
    k_patches: torch.Tensor,
    grid_size: Union[int, Tuple[int, int]] = 14,
) -> Dict[str, Any]:
  """Computes open-vocabulary zero-shot text-to-patch spatial alignment and localized bounding box."""
  device = k_patches.device
  t_tensor = torch.tensor(text_vector, device=device, dtype=torch.float32)
  if t_tensor.dim() == 1:
    t_tensor = F.normalize(t_tensor, p=2, dim=-1)

  # Dimension alignment if text and patch vectors differ
  if k_patches.shape[-1] != t_tensor.shape[-1]:
    min_dim = min(k_patches.shape[-1], t_tensor.shape[-1])
    sims = torch.mv(k_patches[:, :min_dim], t_tensor[:min_dim])
  else:
    sims = torch.mv(k_patches, t_tensor)

  num_p = k_patches.shape[0]
  if isinstance(grid_size, tuple) and grid_size[0] * grid_size[1] == num_p:
    h_g, w_g = grid_size
  else:
    s_dim = int(np.sqrt(num_p))
    h_g = w_g = max(1, s_dim)

  sims_slice = sims[:h_g * w_g]
  heatmap_2d = sims_slice.view(h_g, w_g).cpu().numpy()
  h_min, h_max = heatmap_2d.min(), heatmap_2d.max()
  heatmap_norm = (heatmap_2d - h_min) / (h_max - h_min + 1e-8)

  smoothed = cv2.GaussianBlur(heatmap_norm, (3, 3), 0.75)
  thresh = max(0.52 * float(smoothed.max()), float(smoothed.mean()) + 0.5 * float(smoothed.std()))
  binary = (smoothed >= thresh).astype(np.uint8)

  num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary)
  if num_labels > 1:
    best_label = 1
    best_energy = -1.0
    for l in range(1, num_labels):
      comp_energy = float(heatmap_2d[labels == l].sum())
      if comp_energy > best_energy:
        best_energy = comp_energy
        best_label = l
    y_idx, x_idx = np.where(labels == best_label)
    x1 = round(max(0.0, float(x_idx.min()) / float(w_g)), 3)
    y1 = round(max(0.0, float(y_idx.min()) / float(h_g)), 3)
    x2 = round(min(1.0, float(x_idx.max() + 1) / float(w_g)), 3)
    y2 = round(min(1.0, float(y_idx.max() + 1) / float(h_g)), 3)
    localized_box = [x1, y1, x2, y2]
  else:
    y_idx, x_idx = np.where(heatmap_norm >= 0.55)
    if len(y_idx) > 0:
      x1 = round(max(0.0, float(x_idx.min()) / float(w_g)), 3)
      y1 = round(max(0.0, float(y_idx.min()) / float(h_g)), 3)
      x2 = round(min(1.0, float(x_idx.max() + 1) / float(w_g)), 3)
      y2 = round(min(1.0, float(y_idx.max() + 1) / float(h_g)), 3)
      localized_box = [x1, y1, x2, y2]
    else:
      localized_box = [0.2, 0.2, 0.8, 0.8]

  max_score = round(float(sims.max().item()) * 100.0, 2)
  avg_score = round(float(sims.mean().item()) * 100.0, 2)

  return {
      'max_score': max_score,
      'avg_score': avg_score,
      'localized_box': localized_box,
      'heatmap_2d': heatmap_2d,
  }
