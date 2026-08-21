# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Video processing, SSIM keyframing, and multi-event triage pipeline."""

from typing import Any, Dict, List
import cv2
from flint.engine import FlintEngine
from flint.similarity import cosine_similarity
from PIL import Image


def extract_keyframes_ssim(
    video_path: str, threshold: float = 0.65
) -> List[tuple]:
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
          (timestamp, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
      )
      prev_gray = gray
    else:
      score = cv2.matchTemplate(gray, prev_gray, cv2.TM_CCOEFF_NORMED)[0][0]
      if score < threshold:
        timestamp = frame_idx / fps
        keyframes.append(
            (timestamp, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        )
        prev_gray = gray
    frame_idx += 1

  cap.release()
  return keyframes


def triage_video(
    engine: FlintEngine,
    video_path: str,
    target_embeddings: Dict[str, List[float]],
    method: str = "ssim",
    similarity_threshold: float = 0.80,
) -> List[Dict[str, Any]]:
  keyframes = extract_keyframes_ssim(video_path)
  events = []

  for timestamp, frame_img in keyframes:
    frame_vector = engine.compute_image_embedding(frame_img, normalize=True)
    for label, target_vec in target_embeddings.items():
      score = cosine_similarity(frame_vector, target_vec)
      if score >= similarity_threshold:
        events.append({
            "timestamp_seconds": timestamp,
            "target_label": label,
            "score": score,
        })
  return events
