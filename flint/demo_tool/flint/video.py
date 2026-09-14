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

"""Video processing, multi-strategy keyframing (SSIM, Time Interval, Uniform), and triage."""

from typing import Any, Dict, List, Optional, Tuple
import cv2
from PIL import Image
from flint.engine import FlintEngine
from flint.similarity import cosine_similarity


def extract_keyframes_ssim(
    video_path: str, threshold: float = 0.65
) -> List[Tuple[float, int, Image.Image]]:
  """Extracts keyframes based on structural scene change detection."""
  cap = cv2.VideoCapture(video_path)
  fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
  keyframes = []
  prev_gray = None
  frame_idx = 0

  while True:
    ret, frame = cap.read()
    if not ret:
      break
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if prev_gray is None:
      timestamp = frame_idx / fps
      keyframes.append(
          (timestamp, frame_idx, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
      )
      prev_gray = gray
    else:
      score = cv2.matchTemplate(gray, prev_gray, cv2.TM_CCOEFF_NORMED)[0][0]
      if score < threshold:
        timestamp = frame_idx / fps
        keyframes.append(
            (timestamp, frame_idx, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        )
        prev_gray = gray
    frame_idx += 1

  cap.release()
  return keyframes


def extract_keyframes_interval(
    video_path: str, interval_seconds: float = 1.0
) -> List[Tuple[float, int, Image.Image]]:
  """Extracts keyframes at fixed time intervals (e.g. 1 frame every X seconds)."""
  cap = cv2.VideoCapture(video_path)
  fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
  frame_interval = max(1, int(round(fps * max(0.1, interval_seconds))))
  keyframes = []
  frame_idx = 0

  while True:
    ret, frame = cap.read()
    if not ret:
      break
    if frame_idx % frame_interval == 0:
      timestamp = frame_idx / fps
      keyframes.append(
          (timestamp, frame_idx, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
      )
    frame_idx += 1

  cap.release()
  return keyframes


def extract_keyframes_uniform(
    video_path: str, num_frames: int = 10
) -> List[Tuple[float, int, Image.Image]]:
  """Extracts a fixed number of uniformly spaced keyframes across the video."""
  cap = cv2.VideoCapture(video_path)
  fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
  total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
  if total_frames <= 0:
    return extract_keyframes_interval(video_path, 1.0)

  num_frames = max(1, min(num_frames, total_frames))
  target_indices = set(int(i * total_frames / num_frames) for i in range(num_frames))
  keyframes = []
  frame_idx = 0

  while True:
    ret, frame = cap.read()
    if not ret:
      break
    if frame_idx in target_indices:
      timestamp = frame_idx / fps
      keyframes.append(
          (timestamp, frame_idx, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
      )
    frame_idx += 1

  cap.release()
  return keyframes


def extract_keyframes(
    video_path: str,
    method: str = "ssim",
    ssim_threshold: float = 0.65,
    interval_seconds: float = 1.0,
    uniform_count: int = 10,
) -> List[Tuple[float, int, Image.Image]]:
  """Unified keyframe extraction entrypoint supporting all extraction methods."""
  method = (method or "ssim").lower()
  if method == "interval":
    return extract_keyframes_interval(video_path, interval_seconds=interval_seconds)
  elif method == "uniform":
    return extract_keyframes_uniform(video_path, num_frames=uniform_count)
  else:  # default ssim
    return extract_keyframes_ssim(video_path, threshold=ssim_threshold)


def triage_video(
    engine: FlintEngine,
    video_path: str,
    target_embeddings: Dict[str, List[float]],
    method: str = "ssim",
    ssim_threshold: float = 0.65,
    interval_seconds: float = 1.0,
    uniform_count: int = 10,
    similarity_threshold: float = 0.80,
) -> List[Dict[str, Any]]:
  """Triages video by extracting keyframes using the chosen method and scoring against targets."""
  keyframes = extract_keyframes(
      video_path,
      method=method,
      ssim_threshold=ssim_threshold,
      interval_seconds=interval_seconds,
      uniform_count=uniform_count,
  )
  events = []

  for timestamp, frame_idx, frame_img in keyframes:
    frame_vector = engine.compute_image_embedding(frame_img, normalize=True)
    for label, target_vec in target_embeddings.items():
      score = cosine_similarity(frame_vector, target_vec)
      if score >= similarity_threshold:
        events.append({
            "timestamp_seconds": timestamp,
            "frame_index": frame_idx,
            "target_label": label,
            "score": score,
        })
  return events
