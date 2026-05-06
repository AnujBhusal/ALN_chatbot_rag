# ALN Internal AI Assistant - RAG Chatbot

A FastAPI-based Retrieval-Augmented Generation (RAG) chatbot for Accountability Lab Nepal (ALN), enabling intelligent document ingestion, semantic search, multi-turn conversations with memory, and interview booking functionality.

## 📋 Table of Contents
- [Features](#features)
- [Technology Stack](#technology-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation & Setup](#installation--setup)
- [Environment Configuration](#environment-configuration)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [Development](#development)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

## 🚀 Features

### Core Functionality
- **📄 Document Ingestion**: Upload PDF/TXT files with intelligent text extraction and semantic chunking
- **💬 Conversational RAG**: Multi-turn conversations with document context and persistent memory
- **🔍 Semantic Search**: Vector-based similarity search with metadata-aware filtering
- **📅 Interview Booking**: Schedule interviews with validation and storage
- **🏷️ Smart Metadata**: ALN document-type awareness (donor_proposal, integrity_icon, governance_weekly, etc.)
- **💾 Conversation Memory**: Redis-powered session-based chat history
- **🗃️ Multiple LLM Support**: Groq (default), HuggingFace, and Ollama with fallback mechanisms

### Advanced Features
- **Flexible Chunking**: Sentence-based and sliding window strategies with configurable overlap
- **Query Optimization**: Optional LLM-based query rewriting for improved retrieval
- **Folder Ingestion**: Batch upload and process entire document folders
- **Duplicate Detection**: Automatic handling of duplicate documents
- **Type-Aware Retrieval**: Search results filtered by document type and metadata
- **Role-Based Access**: Support for different user roles (staff, admin, etc.)

## 🛠️ Technology Stack

### Backend
| Component | Technology | Version |
|-----------|-----------|---------|
| **Framework** | FastAPI | 0.104.1 |
| **Server** | Uvicorn | 0.24.0 |
| **Async HTTP Client** | httpx | 0.27.2 |

### AI & ML
| Component | Technology | Details |
|-----------|-----------|---------|
| **LLM Provider** | Groq API | mixtral-8x7b-32768 (default) |
| **LLM Fallbacks** | HuggingFace, Ollama | Auto-fallback on errors |
| **Embeddings** | Sentence-Transformers | all-MiniLM-L6-v2 |
| **Embedding Model Package** | sentence-transformers | 2.7.0 |
| **Numpy (ML ops)** | numpy | 1.24.3 |

### Databases & Storage
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **Vector Database** | Pinecone | 6.0.2 | Semantic search and embeddings |
| **Cache & Sessions** | Redis | 5.0.1 | Conversation memory & caching |
| **Relational DB** | PostgreSQL | 15 (Docker) | Metadata, bookings, users |
| **PostgreSQL Driver** | psycopg2-binary | 2.9.9 | Python-PostgreSQL adapter |

### ORM & Database Tools
| Component | Technology | Version |
|-----------|-----------|---------|
| **ORM** | SQLAlchemy | 2.0.23 |
| **DB URL Parser** | python-dotenv | 1.0.0 |

### Document Processing
| Component | Technology | Version | Purpose |
|-----------|-----------|---------|---------|
| **PDF Parser** | PyPDF2 | 3.0.1 | Text extraction from PDFs |
| **Advanced PDF** | pdfplumber | 0.11.0 | Detailed PDF analysis |

### API & Data Validation
| Component | Technology | Version |
|-----------|-----------|---------|
| **Data Validation** | Pydantic | 2.5.0 (with email support) |
| **File Upload** | python-multipart | 0.0.6 |
| **HTTP Requests** | requests | 2.31.0 |

### Frontend
| Component | Technology | Version |
|-----------|-----------|---------|
| **Library** | React | 18.3.1 |
| **DOM Binding** | react-dom | 18.3.1 |
| **Build Tool** | Vite | 5.4.14 |
| **Language** | TypeScript | 5.9.3 |
| **Styling** | Tailwind CSS | 3.4.17 |
| **CSS Processing** | PostCSS | 8.5.3 |
| **CSS Prefixing** | Autoprefixer | 10.4.20 |

### Containerization & Deployment
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Container Runtime** | Docker | Application containerization |
| **Orchestration** | Docker Compose | Multi-service management |
| **Deployment Platform** | Render (optional) | Cloud deployment support |

### Development Tools
| Component | Technology | Version |
|-----------|-----------|---------|
| **Type Checking** | @types/react | 18.3.18 |
| **Type Checking** | @types/react-dom | 18.3.5 |
| **Vite React Plugin** | @vitejs/plugin-react | 4.3.4 |


## 📁 Project Structure

```
ALN_chatbot_rag/
├── app/                              # Main FastAPI application
│   ├── __init__.py
│   ├── main.py                       # FastAPI app initialization
│   ├── config.py                     # Environment configuration
│   ├── api/                          # API route handlers
│   │   ├── auth.py                   # Authentication endpoints
│   │   ├── chat.py                   # Chat/query endpoints
│   │   ├── ingest.py                 # Document upload endpoints
│   │   └── booking.py                # Interview booking endpoints
│   ├── db/                           # Database layer
│   │   ├── models.py                 # SQLAlchemy models
│   │   └── session.py                # DB session management
│   └── services/                     # Business logic services
│       ├── llm.py                    # LLM integration (Groq)
│       ├── embeddings.py             # Embedding generation
│       ├── retrieval.py              # Document retrieval logic
│       ├── vectorstore.py            # Pinecone management
│       ├── memory.py                 # Redis session management
│       ├── chunking.py               # Text chunking strategies
│       ├── metadata.py               # Metadata handling
│       ├── query_rewriter.py         # Query optimization
│       ├── intent.py                 # Intent detection
│       ├── access_control.py         # Role-based access
│       └── folder_ingestion.py       # Bulk folder processing
├── frontend/                         # React TypeScript frontend
│   ├── src/
│   │   ├── App.tsx                   # Main app component
│   │   ├── main.tsx                  # React entry point
│   │   ├── index.css                 # Global styles
│   │   └── vite-env.d.ts             # Vite env types
│   ├── public/                       # Static assets
│   ├── package.json                  # Frontend dependencies
│   ├── tsconfig.json                 # TypeScript config
│   ├── vite.config.ts                # Vite build config
│   └── tailwind.config.js            # Tailwind CSS config
├── data/                             # Data directory
│   ├── pdfs/                         # Uploaded PDF storage
│   └── synonyms.json                 # Search synonyms
├── scripts/                          # Utility scripts
│   ├── cleanup_old_pdfs.py
│   └── sync_pdfs_to_render.py
├── tests/                            # Test suite
│   ├── test_intent.py
│   └── test_retrieval.py
├── docker-compose.yml                # Multi-service orchestration
├── Dockerfile                        # Application container
├── requirements.txt                  # Python dependencies
├── fly.toml                          # Fly.io deployment config
├── .env                              # Environment variables (gitignored)
└── README.md                         # This file
```

## 📦 Prerequisites

### System Requirements
- **OS**: Windows, macOS, or Linux
- **Memory**: Minimum 4GB RAM (8GB+ recommended)
- **Disk**: 10GB+ free space (for PDFs and vector embeddings)

### Required Software
- **Docker Desktop** (for containerized deployment)
  - [Download Docker Desktop](https://www.docker.com/products/docker-desktop)
- **Python 3.11+** (for local development)
  - [Download Python](https://www.python.org/downloads/)
- **Git** (for cloning the repository)

### API Keys Required
- **Groq API Key** - For LLM functionality (default)
  - Sign up: [console.groq.com](https://console.groq.com)
- **Pinecone API Key** - For vector search
  - Sign up: [pinecone.io](https://pinecone.io)
- **HuggingFace Token** (optional) - For fallback LLM
  - Sign up: [huggingface.co](https://huggingface.co)

## 🔧 Installation & Setup

### Option 1: Docker Setup (Recommended)

#### 1.1 Clone the Repository
```bash
git clone https://github.com/Anuj-Bhusal/Rag-Backend.git
cd Rag-Backend
```

#### 1.2 Create Environment File
```bash
cp .env.template .env
# Edit .env and add your API keys
```

#### 1.3 Start Services
```bash
# Start all services (PostgreSQL, Redis, FastAPI)
docker-compose up -d

# Verify all services are running
docker-compose ps

# View logs
docker-compose logs -f app
```

The application will be available at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:5173 (if running separately)

#### 1.4 Stop Services
```bash
docker-compose down

# To also remove volumes (data)
docker-compose down -v
```

### Option 2: Local Development Setup

#### 2.1 Clone the Repository
```bash
git clone https://github.com/Anuj-Bhusal/Rag-Backend.git
cd Rag-Backend
```

#### 2.2 Set Up Python Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

#### 2.3 Install Dependencies
```bash
pip install -r requirements.txt
```

#### 2.4 Start Local Services
```bash
# Start PostgreSQL and Redis with Docker
docker-compose up -d postgres redis

# In another terminal, run FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### 2.5 Set Up Frontend (Optional)
```bash
cd frontend
npm install
npm run dev
```

Frontend will run at http://localhost:5173

## 🔐 Environment Configuration

### Create .env File
```bash
cp .env.template .env
```

### Required Environment Variables

#### AI & LLM Configuration
```env
# Groq API (Primary LLM)
GROQ_API_KEY=your_groq_api_key_here
USE_GROQ=true
GROQ_MODEL=mixtral-8x7b-32768

# HuggingFace (Fallback LLM)
HF_API_KEY=your_huggingface_token_here
USE_HF=false

# Ollama (Local LLM - optional)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral
USE_OLLAMA=false

# Embeddings Model
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

#### Vector Database Configuration
```env
# Pinecone
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_INDEX=documents
PINECONE_REGION=us-east-1
PINECONE_CLOUD=aws
PINECONE_NAMESPACE=default
VECTOR_STORE=pinecone
```

#### Database Configuration
```env
# PostgreSQL
DB_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/rag

# Redis (Session Store)
REDIS_URL=redis://localhost:6379/0
```

#### Features & Modes
```env
# Query Rewriting (LLM-based optimization)
QUERY_REWRITE_USE_LLM=false

# Folder Ingestion (Bulk upload)
ENABLE_FOLDER_INGESTION=true

# Local Development Mode
LOCAL_MODE=true

# Render Deployment Detection
RENDER=false
```

## ▶️ Running the Application

### With Docker Compose (All-in-One)
```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View FastAPI logs
docker-compose logs -f app

# Stop all services
docker-compose down
```

### Backend Only (Local Development)
```bash
# Ensure venv is activated
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# Run FastAPI development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Only
```bash
cd frontend
npm run dev
```

### Access the Application
- **API Endpoint**: http://localhost:8000
- **Interactive Docs**: http://localhost:8000/docs
- **ReDoc Documentation**: http://localhost:8000/redoc
- **Frontend**: http://localhost:5173

## 📡 API Endpoints

### Document Ingestion
```http
POST /ingest/upload
Content-Type: multipart/form-data

Parameters:
  - file: PDF or TXT file (required)
  - chunk_strategy: "sentence" | "sliding" (optional, default: "sentence")
  - document_type: "donor_proposal" | "integrity_icon" | "governance_weekly" | "internal_policy" | "meeting_notes" | "general" (optional)
  - title: string (optional)
  - year: integer (optional)
  - program_name: string (optional)
  - donor_name: string (optional)

Response:
  {
    "document_id": 123,
    "title": "Document Title",
    "type": "donor_proposal",
    "chunks_created": 45,
    "status": "success"
  }
```

### Chat Query
```http
POST /chat/query
Content-Type: application/json

Request:
  {
    "session_id": "unique_session_id",
    "query": "Your question about the documents",
    "role": "staff",
    "document_type": "donor_proposal" (optional)
  }

Response:
  {
    "answer": "Detailed answer from RAG...",
    "sources": [
      {
        "title": "Document Title",
        "type": "donor_proposal",
        "year": 2023,
        "snippet": "Relevant text excerpt..."
      }
    ],
    "document_context": {
      "id": 12,
      "title": "Document Title",
      "type": "donor_proposal"
    }
  }
```

### Chat History
```http
GET /chat/history/{session_id}

Response:
  {
    "session_id": "unique_session_id",
    "messages": [
      {
        "role": "user",
        "content": "Question",
        "timestamp": "2024-01-15T10:30:00Z"
      },
      {
        "role": "assistant",
        "content": "Answer",
        "timestamp": "2024-01-15T10:30:05Z"
      }
    ]
  }
```

### Interview Booking
```http
POST /booking/create
Content-Type: application/json

Request:
  {
    "name": "John Doe",
    "email": "john@example.com",
    "date": "2024-01-15",
    "time": "14:30"
  }

Response:
  {
    "booking_id": 1,
    "name": "John Doe",
    "email": "john@example.com",
    "date": "2024-01-15",
    "time": "14:30",
    "status": "confirmed"
  }
```

### Authentication
```http
POST /auth/login
Content-Type: application/json

Request:
  {
    "email": "user@example.com",
    "password": "password"
  }

Response:
  {
    "access_token": "jwt_token_here",
    "token_type": "bearer",
    "user_id": 1,
    "role": "staff"
  }
```

## 👨‍💻 Development

### Project Setup
```bash
# Clone repository
git clone https://github.com/Anuj-Bhusal/Rag-Backend.git
cd Rag-Backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate      # Windows

# Install dependencies with dev tools
pip install -r requirements.txt
```

### Code Structure
- **app/api/**: FastAPI route handlers
- **app/services/**: Business logic and integrations
- **app/db/**: Database models and session management
- **frontend/src/**: React components

### Running Tests
```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_retrieval.py

# Run with coverage
pytest --cov=app tests/
```

### Development Workflow
```bash
# Terminal 1: Start PostgreSQL and Redis
docker-compose up -d postgres redis

# Terminal 2: Run FastAPI
uvicorn app.main:app --reload

# Terminal 3: Run Frontend
cd frontend && npm run dev
```

### Key Services

#### Document Ingestion Pipeline
- **File Upload Handler** (`app/api/ingest.py`)
- **PDF Parser** (`PyPDF2`, `pdfplumber`)
- **Text Chunker** (`app/services/chunking.py`)
- **Embeddings Generator** (`app/services/embeddings.py`)
- **Vector Store** (`app/services/vectorstore.py`)

#### Chat Pipeline
- **Query Handler** (`app/api/chat.py`)
- **Memory Manager** (`app/services/memory.py`, Redis)
- **Retriever** (`app/services/retrieval.py`)
- **LLM Integration** (`app/services/llm.py`, Groq)
- **Intent Detector** (`app/services/intent.py`)

## 🚀 Deployment

### Docker Deployment
```bash
# Build and push to Docker Hub
docker build -t your-username/rag-chatbot:latest .
docker push your-username/rag-chatbot:latest

# Or run locally
docker build -t rag-chatbot:latest .
docker run -p 8000:8000 --env-file .env rag-chatbot:latest
```

### Render Deployment
1. Push code to GitHub
2. Connect repository to Render
3. Set environment variables in Render dashboard
4. Deploy using `Dockerfile`

### Fly.io Deployment
```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Deploy
flyctl deploy

# View logs
flyctl logs
```

## 🐛 Troubleshooting

### Common Issues

#### 1. Groq API Connection Error
```
Error: Failed to connect to Groq API
Solution: Verify GROQ_API_KEY is set correctly and API quota not exceeded
```

#### 2. Pinecone Connection Error
```
Error: Connection refused to Pinecone
Solution: Check PINECONE_API_KEY, PINECONE_INDEX, and PINECONE_REGION
```

#### 3. PostgreSQL Connection Error
```
Error: could not connect to server: Connection refused
Solution: Ensure PostgreSQL is running via Docker: docker-compose up -d postgres
```

#### 4. Redis Connection Error
```
Error: connection refused (Errno 111)
Solution: Start Redis: docker-compose up -d redis
```

#### 5. PDF Parsing Error
```
Error: Failed to extract text from PDF
Solution: Verify PDF is not encrypted; use pdfplumber as fallback
```

### Debug Mode
```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
uvicorn app.main:app --reload --log-level debug

# Check service health
curl http://localhost:8000/health
```

### Database Troubleshooting
```bash
# Reset database (WARNING: deletes all data)
docker-compose down -v
docker-compose up -d postgres
python app/db/init_db.py

# Check PostgreSQL logs
docker-compose logs postgres
```

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Groq API Docs](https://console.groq.com/docs)
- [Pinecone Documentation](https://docs.pinecone.io/)
- [Redis Documentation](https://redis.io/docs/)
- [Sentence-Transformers](https://www.sbert.net/)
- [React & Vite Documentation](https://vitejs.dev/guide/)
- [Tailwind CSS Documentation](https://tailwindcss.com/)

## 📝 License

This project is proprietary to Accountability Lab Nepal (ALN).

## 🤝 Contributing

For contribution guidelines, please contact the development team.

## 📧 Support

For issues and questions, please contact the development team or open an issue in the repository.

---

**Last Updated**: May 2026  
**Current Version**: 2.0.0  
**Status**: Production Ready
