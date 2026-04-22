# 🚀 Free Deployment Guide for ALN Chatbot RAG

## Overview
This guide contains all the information needed to deploy the ALN Chatbot RAG project **100% free** on production servers.

---

## 📊 Current Stack & Changes Needed

| Component | Current Setup | Paid? | Free Alternative | Status |
|-----------|---------------|-------|-------------------|--------|
| **Backend** | FastAPI (local) | ❌ | Railway/Render/Fly.io | ⚠️ Needs Config |
| **Frontend** | React (local) | ❌ | Vercel/Netlify | ⚠️ Needs Config |
| **Database** | PostgreSQL (Docker) | ❌ | Railway/Render/Supabase | ⚠️ Needs Config |
| **Cache** | Redis (Docker) | ❌ | Railway/Render | ⚠️ Needs Config |
| **Vector DB** | Qdrant (Docker) | ❌ | Self-hosted | ⚠️ Needs Container |
| **LLM** | Cohere API | 💰 PAID | Ollama/Groq/HuggingFace | 🔴 MUST CHANGE |
| **Embeddings** | sentence-transformers | ❌ | sentence-transformers | ✅ Free |

---

## 🔴 Critical Changes Required

### 1. **Remove Cohere Dependency (PAID - CRITICAL)**

**File**: `requirements.txt`

**Current**:
```
cohere==4.57
```

**Change to** (remove or replace with):
```
# Option 1: Use Ollama locally
# ollama runs on your server

# Option 2: Use Groq (free API)
groq==0.4.1

# Option 3: Use HuggingFace
huggingface-hub==0.17.3
```

**File**: `app/services/llm.py`

**What to change**:
- Remove `cohere` client initialization
- Replace with `groq.Groq()` or local Ollama calls
- Keep HuggingFace fallback

**Example replacement**:
```python
# BEFORE (PAID):
import cohere
client = cohere.Client(api_key=COHERE_API_KEY)

# AFTER (FREE - Groq):
from groq import Groq
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
```

---

### 2. **Docker Compose Optimization for Deployment**

**File**: `docker-compose.yml`

**Changes needed**:
- Add Qdrant to services (currently missing)
- Remove `--reload` from production
- Add health checks
- Optimize resource limits

**Add this service**:
```yaml
qdrant:
  image: qdrant/qdrant:latest
  container_name: rag_qdrant
  ports:
    - "6333:6333"
    - "6334:6334"
  volumes:
    - qdrant_data:/qdrant/storage
  environment:
    QDRANT__SERVICE__HTTP_PORT: 6333
    QDRANT__SERVICE__GRPC_PORT: 6334

volumes:
  qdrant_data:
```

---

### 3. **Environment Variables for Production**

**File**: Create `.env.production`

```ini
# Production Environment Variables

# DATABASE
DB_URL=postgresql://user:password@db-host:5432/rag_db

# REDIS
REDIS_HOST=redis-host
REDIS_PORT=6379
REDIS_URL=redis://default:password@redis-host:6379

# QDRANT
QDRANT_URL=http://qdrant-host:6333

# LLM - Choose ONE option below

# Option 1: Groq (Recommended - Free)
GROQ_API_KEY=your_groq_key_here
USE_GROQ=true

# Option 2: HuggingFace
HF_API_KEY=your_hf_token_here
USE_HF=true

# Option 3: Ollama (Self-hosted)
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral
USE_OLLAMA=false

# Frontend
FRONTEND_URL=https://your-frontend-domain.com

# API
API_PORT=8000
API_HOST=0.0.0.0
```

---

## 🎯 Deployment Options (Choose One)

### **Option 1: Fly.io (RECOMMENDED - Most Complete)**

**Why**: Best free tier, auto-scaling, simple deployment

**Steps**:

1. **Install Fly CLI**
   ```bash
   curl -L https://fly.io/install.sh | sh
   ```

2. **Create `fly.toml` in project root**
   ```toml
   app = "aln-chatbot"
   primary_region = "dfw"

   [build]
   dockerfile = "Dockerfile"

   [env]
   API_PORT = "8000"
   DATABASE_URL = "postgresql://..."
   REDIS_URL = "redis://..."
   GROQ_API_KEY = "your-key"

   [[services]]
   protocol = "tcp"
   internal_port = 8000
   processes = ["app"]

   [[services.ports]]
   port = 80
   handlers = ["http"]

   [[services.ports]]
   port = 443
   handlers = ["tls", "http"]
   force_https = true

   [checks]
   [checks.http_check]
   grace_period = "5s"
   interval = "30s"
   method = "get"
   path = "/docs"
   protocol = "http"
   timeout = "5s"
   type = "http"
   ```

3. **Deploy**
   ```bash
   fly auth login
   fly launch
   fly deploy
   ```

4. **Add Postgres & Redis**
   ```bash
   fly postgres create --name aln-db
   fly redis create --name aln-redis
   ```

5. **Set Secrets**
   ```bash
   fly secrets set GROQ_API_KEY=your_key
   fly secrets set FRONTEND_URL=https://your-frontend.vercel.app
   ```

---

### **Option 2: Railway (Easiest Setup)**

**Why**: Pre-built services, easy UI, $5/month free credits

**Steps**:

1. Go to railway.app
2. Create new project
3. Connect GitHub repository
4. Add services:
   - PostgreSQL
   - Redis
   - Docker (Backend)
5. Environment variables → Add from `.env.production`
6. Deploy

---

### **Option 3: Render + Vercel**

**Backend on Render**:
1. Go to render.com
2. Create new Web Service
3. Connect repository
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn app.main:app --host 0.0.0.0`
6. Add PostgreSQL service
7. Add Redis service

**Frontend on Vercel**:
1. Go to vercel.com
2. Import project
3. Root directory: `frontend`
4. Environment: `VITE_API_BASE_URL=https://your-backend.onrender.com/api`
5. Deploy

---

## 📝 Code Changes Checklist

### Required Changes:

- [ ] Remove `cohere==4.57` from `requirements.txt`
- [ ] Add `groq==0.4.1` to `requirements.txt`
- [ ] Update `app/services/llm.py` to use Groq/Ollama
- [ ] Update `app/config.py` to support new LLM options
- [ ] Create `.env.production` file
- [ ] Create `fly.toml` or deployment config
- [ ] Update `docker-compose.yml` for production
- [ ] Add `Dockerfile` optimization (multi-stage build)
- [ ] Update `frontend/.env` with production API URL
- [ ] Add database migration script (if needed)
- [ ] Create `DEPLOYMENT_CHECKLIST.md`

### Optional Improvements:

- [ ] Add GitHub Actions for CI/CD
- [ ] Add monitoring/logging (Sentry, LogRocket)
- [ ] Add uptime monitoring
- [ ] Setup auto-scaling
- [ ] Add rate limiting
- [ ] Enable CORS for production
- [ ] Setup email notifications

---

## 🔧 Specific File Changes

### `requirements.txt`

**Remove**:
```
cohere==4.57
```

**Add**:
```
groq==0.4.1  # For free LLM API
python-dotenv==1.0.0  # Already there, ensure it's present
```

---

### `app/services/llm.py`

**Key changes**:

1. Replace Cohere imports with Groq
2. Update `call_llm()` method
3. Add Groq API calls
4. Keep HuggingFace fallback

**Example structure**:
```python
from groq import Groq
import os

class LLMService:
    def __init__(self):
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    def call_llm(self, prompt: str) -> str:
        try:
            response = self.groq_client.chat.completions.create(
                model="mixtral-8x7b-32768",  # Free model
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            # Fallback to HuggingFace
            return self._fallback_response(prompt)
```

---

### `Dockerfile` (Create if not exists)

```dockerfile
# Multi-stage build
FROM python:3.11-slim as builder

WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim

WORKDIR /code
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY app ./app
COPY .env.production .env

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### `docker-compose.prod.yml` (For local testing)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: rag
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

  app:
    build: .
    ports:
      - "8000:8000"
    env_file: .env.production
    depends_on:
      - postgres
      - redis
      - qdrant

volumes:
  postgres_data:
  redis_data:
  qdrant_data:
```

---

## ✅ Free Tier Limits Summary

| Service | Free Limit | Notes |
|---------|-----------|-------|
| **Fly.io** | 3 shared CPUs, 3GB RAM | Enough for this project |
| **Railway** | $5/month | Usually covers full stack |
| **Render** | 1 web service, 0.5GB DB | Limited but free |
| **Vercel** | Unlimited deployments | Frontend only |
| **Groq API** | 30 requests/min | Free tier, no credit card |
| **Postgres** | 5GB storage | Usually enough |
| **Redis** | Included in deployment | No separate cost |

---

## 🚀 Deployment Checklist

Before deploying:

- [ ] All Cohere references removed
- [ ] Groq API key obtained (groq.com)
- [ ] `.env.production` created and tested locally
- [ ] `docker-compose.prod.yml` works locally
- [ ] Frontend points to correct backend URL
- [ ] Database migrations run
- [ ] Health checks pass
- [ ] API docs accessible
- [ ] Frontend loads correctly
- [ ] Chat functionality works end-to-end
- [ ] Document upload works
- [ ] No sensitive data in git
- [ ] CORS configured correctly
- [ ] Rate limiting enabled
- [ ] Error handling in place
- [ ] Monitoring setup (optional)

---

## 📞 Support & Resources

**Free LLM APIs**:
- Groq: https://console.groq.com/keys
- HuggingFace: https://huggingface.co/settings/tokens
- Ollama: https://ollama.ai

**Deployment Platforms**:
- Fly.io: https://fly.io/docs/
- Railway: https://docs.railway.app/
- Render: https://render.com/docs
- Vercel: https://vercel.com/docs

**Framework Docs**:
- FastAPI: https://fastapi.tiangolo.com/deployment/
- React: https://vitejs.dev/guide/ssr.html

---

## 🎯 Next Steps

1. **Choose deployment platform** (Fly.io recommended)
2. **Make code changes** listed in this guide
3. **Test locally** with `docker-compose.prod.yml`
4. **Push to GitHub**
5. **Connect to deployment platform**
6. **Set environment variables**
7. **Deploy and monitor**

---

**Last Updated**: April 22, 2026  
**Status**: Ready for Free Deployment ✅
