from typing import List, Protocol


class EmbeddingProvider(Protocol):
    def embed(self, texts: List[str]) -> List[List[float]]:
        """Return one normalized embedding per input text."""


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str, device: str) -> None:
        self.model_name = model_name
        self.device = device
        self._model = None

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise RuntimeError(
                    "vector retrieval dependencies are unavailable; "
                    "install demo/api/requirements-vector.txt"
                ) from e
            self._model = SentenceTransformer(self.model_name, device=self.device)

        vectors = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()
