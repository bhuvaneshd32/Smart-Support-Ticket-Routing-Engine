# ml/embedding_model.py

from sentence_transformers import SentenceTransformer
import torch

_device = "cuda" if torch.cuda.is_available() else "cpu"

_embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2",
    device=_device
)


def get_embedding(text: str) -> list:
    if not text.strip():
        return []

    with torch.no_grad():
        embedding = _embedding_model.encode(text)

    return embedding.tolist()
