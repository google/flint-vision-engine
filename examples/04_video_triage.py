# Copyright 2026 Google LLC
# Licensed under Apache 2.0

"""Example 4: Video triage using Structural Similarity (SSIM) scene change detection."""

import cv2
from PIL import Image


def extract_keyframes_ssim(video_path, threshold=0.65):
  """Decomposes video into structural snapshots using scene-change detection."""
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
      # Lightweight score check between consecutive frames
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
