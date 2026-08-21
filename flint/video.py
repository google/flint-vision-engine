import cv2, numpy as np
from PIL import Image
class KeyframeExtractor:
    def __init__(self, fps=1.0):
        self.fps = fps
    def extract_keyframes(self, path):
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        interval = int(fps / self.fps)
        keyframes, count = [], 0
        while True:
            ret, frame = cap.read()
            if not ret: break
            if count % interval == 0:
                keyframes.append((count/fps, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))))
            count += 1
        cap.release()
        return keyframes
class VideoProcessor:
    def __init__(self, ext=None):
        self.ext = ext or KeyframeExtractor()
    def process(self, path): return self.ext.extract_keyframes(path)
