from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys

from app.db.session import init_db
from app.api import ingest, chat, booking, auth
from app import config
from app.services.folder_ingestion import FolderIngestionService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Log environment check
logger.info(f"GROQ_API_KEY present: {bool(config.GROQ_API_KEY)}")
logger.info(f"PINECONE_API_KEY present: {bool(config.PINECONE_API_KEY)}")
logger.info(f"DB_URL present: {bool(config.DB_URL)}")
logger.info(f"REDIS_URL present: {bool(config.REDIS_URL)}")

app = FastAPI(
    title="RAG Backend API",
    description="A Retrieval-Augmented Generation backend with document ingestion, conversational AI, and booking functionality",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware - Allow all origins for public API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins (public API)
    allow_credentials=False,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],
    max_age=600,
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
app.include_router(auth.router, prefix="/api")

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


@app.on_event("startup")
async def startup_event():
    """Auto-ingest PDFs from ./data/pdfs folder if running locally."""
    if config.LOCAL_MODE and config.ENABLE_FOLDER_INGESTION:
        logger.info("\n" + "=" * 80)
        logger.info("📚 LOCAL MODE DETECTED - Auto-ingesting PDFs from ./data/pdfs")
        logger.info("=" * 80)
        
        try:
            ingestion_service = FolderIngestionService()
            results = ingestion_service.ingest_folder()
            
            logger.info("\n" + "=" * 80)
            logger.info("📊 FOLDER INGESTION SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Total PDFs: {results['total']}")
            logger.info(f"✅ Successful: {results['successful']}")
            logger.info(f"❌ Failed: {results['failed']}")
            
            for doc in results['documents']:
                status_icon = "✅" if doc['status'] == 'ingested' else "⏭️"
                logger.info(f"{status_icon} {doc['title']} (ID: {doc['id']}, {doc['chunks']} chunks)")
            
            logger.info("=" * 80 + "\n")
        
        except Exception as e:
            logger.error(f"❌ Folder ingestion failed: {e}", exc_info=True)
    else:
        if not config.LOCAL_MODE:
            logger.info("🌍 Production mode - folder ingestion disabled")
        elif not config.ENABLE_FOLDER_INGESTION:
            logger.info("⏭️  Folder ingestion disabled by ENABLE_FOLDER_INGESTION=false")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
