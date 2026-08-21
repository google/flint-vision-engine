import numpy as np
def cosine_similarity(a, b):
    a_n = a / np.clip(np.linalg.norm(a, axis=-1, keepdims=True), 1e-12, None)
    b_n = b / np.clip(np.linalg.norm(b, axis=-1, keepdims=True), 1e-12, None)
    return np.dot(a_n, b_n.T)
def batch_similarity(q, c): return cosine_similarity(q if q.ndim==2 else q.reshape(1,-1), c).squeeze(0)
def find_top_k(q, c, k=5):
    s = batch_similarity(q, c)
    top = np.argsort(s)[::-1][:k]
    return [(int(i), float(s[i])) for i in top]
