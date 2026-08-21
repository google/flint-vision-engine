import numpy as np
from flint.similarity import find_top_k
class VectorIndex:
    def __init__(self, dim):
        self.dim = dim
        self.vectors = np.empty((0, dim), dtype=np.float32)
        self.metadata = []
    def add(self, vec, meta=None):
        self.vectors = np.vstack([self.vectors, vec if vec.ndim==2 else vec.reshape(1,-1)])
        self.metadata.append(meta)
    def search(self, q, k=5):
        return [(i, s, self.metadata[i]) for i, s in find_top_k(q, self.vectors, k=k)]
class CrossModalSearch:
    def __init__(self, engine):
        self.engine = engine
        self.index = None
    def index_images(self, imgs, meta=None):
        res = self.engine.embed_images(imgs)
        self.index = VectorIndex(res.dimension)
        for i in range(len(imgs)):
            self.index.add(res.embeddings[i], meta[i] if meta else {"index": i})
    def query_text(self, text, k=5):
        emb = self.engine.embed_text(text).embeddings[0]
        return self.index.search(emb, k=k)
