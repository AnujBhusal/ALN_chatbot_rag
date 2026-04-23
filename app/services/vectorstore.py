from typing import List, Dict, Any, Optional
import os
from pinecone import Pinecone, ServerlessSpec
import logging
import time

logger = logging.getLogger(__name__)

class VectorStoreService:
    """Handles storing and querying embeddings in Pinecone."""

    def __init__(self, collection_name: str = "documents"):
        self.api_key = os.getenv("PINECONE_API_KEY", "")
        self.region = os.getenv("PINECONE_REGION", "us-east-1")
        self.cloud = os.getenv("PINECONE_CLOUD", "aws")
        self.namespace = os.getenv("PINECONE_NAMESPACE", "default")
        self.collection_name = os.getenv("PINECONE_INDEX", collection_name)
        self.client: Optional[Pinecone] = None
        self.index = None
        self._collection_ensured = False
        logger.info("Initialized VectorStoreService for Pinecone")

    def _init_client(self) -> None:
        """Initialize Pinecone client with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if not self.api_key:
                    raise ValueError("PINECONE_API_KEY is not configured")

                self.client = Pinecone(api_key=self.api_key)
                index_names = self.client.list_indexes().names()
                logger.info("Successfully connected to Pinecone")
                logger.info(f"Available indexes: {index_names}")
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} to connect to Pinecone failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait 2 seconds between retries
                else:
                    logger.error(f"Failed to connect to Pinecone after all retries. Last error: {e}")
                    self.client = None
                    self.index = None

    def _ensure_collection_exists(self) -> None:
        """Ensure the index exists, create if not."""
        if not self.client or self._collection_ensured:
            return
            
        try:
            index_names = self.client.list_indexes().names()
            
            if self.collection_name not in index_names:
                self.client.create_index(
                    name=self.collection_name,
                    dimension=384,
                    metric="cosine",
                    spec=ServerlessSpec(cloud=self.cloud, region=self.region),
                )
                logger.info(f"Created Pinecone index: {self.collection_name}")

            self.index = self.client.Index(self.collection_name)
            
            self._collection_ensured = True
        except Exception as e:
            logger.error(f"Error ensuring index exists: {e}")

    def _ensure_connected(self) -> bool:
        """Ensure we have a working connection to Pinecone."""
        if not self.client:
            self._init_client()
        
        if self.client and (not self._collection_ensured or self.index is None):
            self._ensure_collection_exists()
            
        return self.client is not None and self.index is not None

    def add_documents(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]], ids: List[int]) -> None:
        """Add documents to the vector store."""
        if not self._ensure_connected():
            logger.warning("Pinecone not available, skipping document addition")
            return
            
        try:
            vectors = [
                {"id": str(id_), "values": emb, "metadata": meta}
                for id_, emb, meta in zip(ids, embeddings, metadatas)
            ]
            self.index.upsert(vectors=vectors, namespace=self.namespace)
            logger.info(f"Added {len(vectors)} documents to vector store")
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")

    def upsert_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        """Upsert embeddings with auto-generated IDs."""
        if not self._ensure_connected():
            logger.warning("Pinecone not available, skipping embedding upsert")
            return
            
        try:
            vectors = []
            for i, (emb, meta) in enumerate(zip(embeddings, metadatas)):
                doc_id = meta.get('document_id', 0)
                chunk_id = meta.get('chunk_id', i)
                point_id = f"{doc_id}_{chunk_id}"
                vectors.append({"id": point_id, "values": emb, "metadata": meta})
            
            self.index.upsert(vectors=vectors, namespace=self.namespace)
            logger.info(f"Upserted {len(vectors)} embeddings to vector store")
        except Exception as e:
            logger.error(f"Error upserting embeddings: {e}")

    def query(self, embedding: List[float], top_k: int = 5, query_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Query the vector store for similar documents."""
        if not self._ensure_connected():
            logger.warning("Pinecone not available, returning empty results")
            return []
            
        try:
            result = self.index.query(
                vector=embedding,
                top_k=top_k,
                namespace=self.namespace,
                include_metadata=True,
                filter=query_filter,
            )
            matches = result.get("matches", []) if isinstance(result, dict) else getattr(result, "matches", [])
            logger.info(f"Retrieved {len(matches)} results from vector store")
            return [
                {
                    "id": getattr(match, "id", None) if not isinstance(match, dict) else match.get("id"),
                    "score": getattr(match, "score", None) if not isinstance(match, dict) else match.get("score"),
                    "metadata": getattr(match, "metadata", {}) if not isinstance(match, dict) else match.get("metadata", {}),
                }
                for match in matches
            ]
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
            return []

    def delete_by_document_id(self, document_id: int):
        """Delete all vectors for a specific document."""
        if not self._ensure_connected():
            logger.warning("Pinecone not available, skipping deletion")
            return
            
        try:
            self.index.delete(
                filter={"document_id": {"$eq": document_id}},
                namespace=self.namespace,
            )
            logger.info(f"Deleted vectors for document {document_id}")
            
        except Exception as e:
            logger.error(f"Error deleting document vectors: {e}")
            raise
