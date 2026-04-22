from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import os
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct, VectorParams, Distance, Filter
from qdrant_client.http.exceptions import UnexpectedResponse, ResponseHandlingException
import logging
import time

logger = logging.getLogger(__name__)

class VectorStoreService:
    """Handles storing and querying embeddings in Qdrant."""

    def __init__(self, host: str = "localhost", port: int = 6333, collection_name: str = "documents"):
        qdrant_url = os.getenv("QDRANT_URL")
        if qdrant_url:
            parsed_url = urlparse(qdrant_url)
            self.host = parsed_url.hostname or host
            self.port = parsed_url.port or port
        else:
            self.host = host
            self.port = port
        self.collection_name = collection_name
        self.client = None
        self._collection_ensured = False
        logger.info(f"Initialized VectorStoreService for {host}:{port}")

    def _init_client(self) -> None:
        """Initialize Qdrant client with retry logic."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                self.client = QdrantClient(host=self.host, port=self.port)
                # Test connection with a simple ping
                collections_response = self.client.get_collections()
                logger.info(f"Successfully connected to Qdrant at {self.host}:{self.port}")
                logger.info(f"Available collections: {[col.name for col in collections_response.collections]}")
                return
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} to connect to Qdrant failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait 2 seconds between retries
                else:
                    logger.error(f"Failed to connect to Qdrant after all retries. Last error: {e}")
                    self.client = None

    def _ensure_collection_exists(self) -> None:
        """Ensure the collection exists, create if not."""
        if not self.client or self._collection_ensured:
            return
            
        try:
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                # Create collection with appropriate vector size (384 for hash embeddings)
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                )
                logger.info(f"Created collection: {self.collection_name}")
            
            self._collection_ensured = True
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")

    def _ensure_connected(self) -> bool:
        """Ensure we have a working connection to Qdrant."""
        if not self.client:
            self._init_client()
        
        if self.client and not self._collection_ensured:
            self._ensure_collection_exists()
            
        return self.client is not None

    def add_documents(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]], ids: List[int]) -> None:
        """Add documents to the vector store."""
        if not self._ensure_connected():
            logger.warning("Qdrant not available, skipping document addition")
            return
            
        try:
            points = [
                PointStruct(id=id_, vector=emb, payload=meta) 
                for id_, emb, meta in zip(ids, embeddings, metadatas)
            ]
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"Added {len(points)} documents to vector store")
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {e}")

    def upsert_embeddings(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        """Upsert embeddings with auto-generated IDs."""
        if not self._ensure_connected():
            logger.warning("Qdrant not available, skipping embedding upsert")
            return
            
        try:
            # Use hash of metadata as unique ID to avoid collisions
            points = []
            for i, (emb, meta) in enumerate(zip(embeddings, metadatas)):
                # Create a unique ID based on document and chunk info
                doc_id = meta.get('document_id', 0)
                chunk_id = meta.get('chunk_id', i)
                point_id = hash(f"{doc_id}_{chunk_id}") % (2**31)  # Ensure positive 32-bit int
                points.append(PointStruct(id=point_id, vector=emb, payload=meta))
            
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"Upserted {len(points)} embeddings to vector store")
        except Exception as e:
            logger.error(f"Error upserting embeddings: {e}")

    def query(self, embedding: List[float], top_k: int = 5, query_filter: Optional[Filter] = None) -> List[Dict[str, Any]]:
        """Query the vector store for similar documents."""
        if not self._ensure_connected():
            logger.warning("Qdrant not available, returning empty results")
            return []
            
        try:
            result = self.client.search(
                collection_name=self.collection_name, 
                query_vector=embedding, 
                limit=top_k,
                query_filter=query_filter,
            )
            logger.info(f"Retrieved {len(result)} results from vector store")
            return [{"id": p.id, "score": p.score, "metadata": p.payload} for p in result]
        except Exception as e:
            logger.error(f"Error querying vector store: {e}")
            return []

    def delete_by_document_id(self, document_id: int):
        """Delete all vectors for a specific document."""
        if not self._ensure_connected():
            logger.warning("Qdrant not available, skipping deletion")
            return
            
        try:
            from qdrant_client.http import models as rest
            
            # Delete points with matching document_id in metadata
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=rest.FilterSelector(
                    filter=rest.Filter(
                        must=[
                            rest.FieldCondition(
                                key="document_id",
                                match=rest.MatchValue(value=document_id)
                            )
                        ]
                    )
                )
            )
            logger.info(f"Deleted vectors for document {document_id}")
            
        except Exception as e:
            logger.error(f"Error deleting document vectors: {e}")
            raise
