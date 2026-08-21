from flint import VisionEngine
from PIL import Image
engine = VisionEngine()
img = Image.new("RGB", (224, 224), color="blue")
res = engine.embed_images(img)
print(f"Embedding shape: {res.embeddings.shape}")
