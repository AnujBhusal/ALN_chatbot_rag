from dotenv import load_dotenv
import os
from typing import List
import requests
import logging
import hashlib

logger = logging.getLogger(__name__)
load_dotenv()

class EmbeddingService:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.embedding_dim = 384
        self.local_model = None
        self._model_loaded = False

        self.use_hf = os.getenv("USE_HF", "false").lower() == "true"
        self.hf_api_key = os.getenv("HF_API_KEY", "")

        self.use_ollama = os.getenv("USE_OLLAMA", "false").lower() == "true"
        self.ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        self.ollama_embedding_model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

        if self.use_hf and self.hf_api_key:
            self.hf_url = f"https://api-inference.huggingface.co/models/{self.model_name}"
            self.hf_headers = {"Authorization": f"Bearer {self.hf_api_key}"}
            logger.info(f"Using HuggingFace API for embeddings: {self.model_name}")
        else:
            self.hf_url = ""
            self.hf_headers = {}

        if self.use_ollama:
            logger.info(f"Ollama embeddings enabled with model: {self.ollama_embedding_model}")

    def _get_local_model(self):
        """Lazy-load the SentenceTransformer model on first use."""
        if not self._model_loaded:
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore
                self.local_model = SentenceTransformer(self.model_name)
                self.embedding_dim = 384
                logger.info(f"Loaded local SentenceTransformer: {self.model_name}")
            except Exception as e:
                logger.warning(f"Could not load local model: {e}")
                self.local_model = None
            finally:
                self._model_loaded = True  # Don't retry on failure
        return self.local_model

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a list of texts."""
        if not texts:
            return []

        local_model = self._get_local_model()
        if local_model:
            embeddings = local_model.encode(texts).tolist()
            self.embedding_dim = len(embeddings[0]) if embeddings else self.embedding_dim
            logger.info(f"Generated {len(embeddings)} embeddings via SentenceTransformer")
            return embeddings

        if self.use_ollama:
            embeddings = self._embed_with_ollama(texts)
            if embeddings:
                return embeddings

        if self.use_hf and self.hf_api_key:
            return self._embed_with_huggingface(texts)

        logger.warning("All embedding providers failed, falling back to hash embeddings")
        return self._embed_with_hash(texts)

    def _embed_with_ollama(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Ollama /api/embeddings endpoint."""
        embeddings: List[List[float]] = []
        try:
            for text in texts:
                response = requests.post(
                    f"{self.ollama_url}/api/embeddings",
                    json={"model": self.ollama_embedding_model, "prompt": text},
                    timeout=20,
                )
                if response.status_code != 200:
                    logger.warning(f"Ollama embedding error: {response.status_code} - {response.text}")
                    return []

                vector = response.json().get("embedding", [])
                if not vector:
                    return []
                embeddings.append(vector)

            if embeddings:
                self.embedding_dim = len(embeddings[0])
                logger.info(f"Generated {len(embeddings)} embeddings via Ollama")
            return embeddings
        except Exception as e:
            logger.warning(f"Error with Ollama embeddings: {e}")
            return []

    def _embed_with_huggingface(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using HuggingFace API."""
        try:
            response = requests.post(
                self.hf_url,
                headers=self.hf_headers,
                json={"inputs": texts, "options": {"wait_for_model": True}},
                timeout=30
            )

            if response.status_code == 200:
                embeddings = response.json()
                if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
                    self.embedding_dim = len(embeddings[0])
                    logger.info(f"Generated {len(embeddings)} embeddings via HuggingFace API")
                    return embeddings
                logger.warning("Unexpected HuggingFace embedding response shape, falling back")
                return self._embed_with_hash(texts)
            else:
                logger.warning(f"HuggingFace API error: {response.status_code}, falling back to hash embeddings")
                return self._embed_with_hash(texts)

        except Exception as e:
            logger.error(f"Error with HuggingFace API: {e}, falling back to hash embeddings")
            return self._embed_with_hash(texts)

    def _embed_with_hash(self, texts: List[str]) -> List[List[float]]:
        """Generate simple hash-based embeddings for texts."""
        embeddings = []

        for text in texts:
            text_hash = hashlib.sha256(text.encode()).hexdigest()

            embedding = []
            for i in range(0, len(text_hash), 2):
                hex_pair = text_hash[i:i+2]
                value = (int(hex_pair, 16) / 255.0) - 0.5
                embedding.append(value)

            target_dim = self.embedding_dim
            while len(embedding) < target_dim:
                embedding.extend(embedding[:min(len(embedding), target_dim - len(embedding))])

            embedding = embedding[:target_dim]

            norm = sum(x*x for x in embedding) ** 0.5
            if norm > 0:
                embedding = [x/norm for x in embedding]

            embeddings.append(embedding)

        logger.info(f"Generated {len(embeddings)} hash-based embeddings")
        return embeddings