from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys

from app.db.session import init_db
from app.api import ingest, chat, booking

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Backend API",
    description="A Retrieval-Augmented Generation backend with document ingestion, conversational AI, and booking functionality",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware - Allow frontend URLs
allowed_origins = [
    "https://aln-chatbot-rag.vercel.app",  # Production frontend
    "https://*.vercel.app",  # Vercel preview deployments
    "http://localhost:5173",  # Local development (Vite)
    "http://localhost:3000",  # Local development (alternative)
    "http://127.0.0.1:5173",  # Local development (127.0.0.1)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    max_age=3600,  # Cache preflight for 1 hour
)

# Initialize DB
try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")
    raise

# Include routers
app.include_router(ingest.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(booking.router, prefix="/api")

@app.get("/")
async def root():
    return {
        "message": "RAG Backend API", 
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "RAG Backend is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
