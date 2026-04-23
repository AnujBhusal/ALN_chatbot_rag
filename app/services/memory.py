from typing import List, Dict
import redis
from redis import ConnectionPool
import os
import json
import logging

logger = logging.getLogger(__name__)

class MemoryService:
    """Handles chat memory using Redis."""

    def __init__(self):
        redis_url = os.getenv("REDIS_URL")
        
        if redis_url:
            try:
                # Use Upstash Redis URL directly
                self.redis_client = redis.from_url(redis_url, decode_responses=True, ssl_certfile=False)
                logger.info("Connected to Redis via REDIS_URL")
            except Exception as e:
                logger.error(f"Failed to connect to Redis via URL: {e}")
                self.redis_client = None
        else:
            # Fall back to individual env vars
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", 6379))
            redis_db = int(os.getenv("REDIS_DB", 0))
            try:
                self.redis_client = redis.Redis(
                    host=redis_host, 
                    port=redis_port, 
                    db=redis_db, 
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True
                )
                logger.info(f"Connected to Redis at {redis_host}:{redis_port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.redis_client = None

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        """Return list of previous messages."""
        if not self.redis_client:
            logger.warning(f"Redis unavailable, returning empty history for {session_id}")
            return []
        
        try:
            data = self.redis_client.get(session_id)
            return json.loads(data) if data else []
        except Exception as e:
            logger.error(f"Error getting history: {e}")
            return []

    def add_message(self, session_id: str, role: str, message: str) -> None:
        """Add a message to the Redis memory."""
        if not self.redis_client:
            logger.warning("Redis unavailable, skipping message storage")
            return
        
        try:
            history = self.get_history(session_id)
            history.append({"role": role, "message": message})
            self.redis_client.set(session_id, json.dumps(history), ex=86400)  # 24-hour expiry
        except Exception as e:
            logger.error(f"Error adding message: {e}")
