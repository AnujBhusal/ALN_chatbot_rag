from dotenv import load_dotenv
import os

load_dotenv()

HF_API_KEY: str = os.getenv("HF_API_KEY", "")
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
PINECONE_API_KEY: str = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX: str = os.getenv("PINECONE_INDEX", "documents")
PINECONE_REGION: str = os.getenv("PINECONE_REGION", "us-east-1")
PINECONE_CLOUD: str = os.getenv("PINECONE_CLOUD", "aws")
PINECONE_NAMESPACE: str = os.getenv("PINECONE_NAMESPACE", "default")
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
VECTOR_STORE: str = os.getenv("VECTOR_STORE", "pinecone")
DB_URL: str = os.getenv("DB_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/rag")

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LLM_MODEL: str = os.getenv("LLM_MODEL", "mixtral-8x7b-32768")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", LLM_MODEL)
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "mistral")

USE_GROQ: bool = os.getenv("USE_GROQ", "true").lower() == "true"
USE_HF: bool = os.getenv("USE_HF", "false").lower() == "true"
USE_OLLAMA: bool = os.getenv("USE_OLLAMA", "false").lower() == "true"

# Local vs Production - auto-detect or override with env var
RENDER_ENVIRONMENT = os.getenv("RENDER", "false").lower() == "true"  # True if running on Render
LOCAL_MODE: bool = os.getenv("LOCAL_MODE", "false").lower() == "true" or not RENDER_ENVIRONMENT
ENABLE_FOLDER_INGESTION: bool = os.getenv("ENABLE_FOLDER_INGESTION", "true").lower() == "true"
# Query rewriting: enable LLM-based rewrite (default: false to avoid latency)
QUERY_REWRITE_USE_LLM: bool = os.getenv("QUERY_REWRITE_USE_LLM", "false").lower() == "true"
