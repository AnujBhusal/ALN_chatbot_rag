# 🚀 Quick Start: Deploy to Fly.io (Free)

This is the fastest way to deploy your project **completely free**.

---

## ⚡ 5-Minute Setup

### Step 1: Get Your Free API Key

Go to https://console.groq.com/keys and create a new API key. This is free and instant.

### Step 2: Install Fly CLI

```bash
# On Windows (PowerShell)
iwr https://fly.io/install.ps1 -useb | iex

# On Mac/Linux
curl -L https://fly.io/install.sh | sh
```

### Step 3: Login to Fly.io

```bash
fly auth login
# Opens browser for login, create free account if needed
```

### Step 4: Create fly.toml

In your project root, create `fly.toml`:

```toml
app = "aln-chatbot-rag"
primary_region = "dfw"

[build]
dockerfile = "Dockerfile"

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

[env]
API_PORT = "8000"
API_HOST = "0.0.0.0"
ENV = "production"
USE_GROQ = "true"
FRONTEND_URL = "https://your-frontend.vercel.app"

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

### Step 5: Create Dockerfile (if not exists)

Create `Dockerfile` in project root:

```dockerfile
FROM python:3.11-slim

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY .env.production .env

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 6: Create Postgres Database

```bash
fly postgres create --name aln-db --region dfw
# Note the DATABASE_URL it gives you
```

### Step 7: Create Redis

```bash
fly redis create --name aln-redis --region dfw
# Note the REDIS_URL it gives you
```

### Step 8: Set Environment Variables

```bash
# Set Groq API key
fly secrets set GROQ_API_KEY=your_groq_key_here

# Set database URLs (get these from above commands)
fly secrets set DB_URL=postgresql://postgres:password@aln-db.internal:5432/postgres
fly secrets set REDIS_URL=redis://default:password@aln-redis.internal:6379

# Set Qdrant URL (will be localhost in container)
fly secrets set QDRANT_URL=http://localhost:6333

# Set frontend URL
fly secrets set FRONTEND_URL=https://your-frontend.vercel.app
```

### Step 9: Deploy

```bash
fly deploy
```

### Step 10: Check Status

```bash
fly status
fly logs
```

### Step 11: Get Your URL

```bash
fly info
# Shows your app URL like: https://aln-chatbot-rag.fly.dev
```

---

## 🎯 Deploy Frontend to Vercel

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Ready for deployment"
git push origin main
```

### Step 2: Go to Vercel

1. Visit https://vercel.com
2. Sign in with GitHub
3. Click "New Project"
4. Select your repository
5. Fill in settings:
   - **Framework Preset**: Other
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`

### Step 3: Add Environment Variable

Add this in Vercel project settings:

```
VITE_API_BASE_URL=https://aln-chatbot-rag.fly.dev/api
```

### Step 4: Deploy

Click "Deploy" - it will auto-deploy from git

---

## ✅ Testing

Once deployed, test your endpoints:

```bash
# Backend API Docs
https://aln-chatbot-rag.fly.dev/docs

# Frontend
https://your-app.vercel.app
```

---

## 📊 Estimated Costs

| Service | Free Limit | Cost |
|---------|-----------|------|
| Fly.io | 3 shared CPUs, 3GB RAM | **$0** |
| PostgreSQL | 3GB storage | Included |
| Redis | Included | Included |
| Groq API | 30 req/min | **$0** |
| Vercel | Unlimited deployments | **$0** |
| **Total** | | **$0/month** ✅ |

---

## 🔧 Common Commands

```bash
# View logs
fly logs

# SSH into app
fly ssh console

# Scale app
fly scale count 2

# View secrets
fly secrets list

# Update secret
fly secrets set KEY=value

# Redeploy
fly deploy

# Destroy app
fly destroy aln-chatbot-rag
```

---

## 🚨 Troubleshooting

**App won't start?**
```bash
fly logs
# Check for errors
```

**Database connection fails?**
```bash
fly secrets set DB_URL=correct_url
fly deploy
```

**Out of memory?**
```bash
fly machine stop app-xxx
fly machine delete app-xxx
fly deploy
```

---

## 📚 Next Steps

1. ✅ Deploy backend to Fly.io
2. ✅ Deploy frontend to Vercel
3. ✅ Set up monitoring (optional)
4. ✅ Add custom domain (optional)
5. ✅ Setup auto-scaling (optional)

---

## 💡 Pro Tips

- Use `fly deploy --build-only` to just rebuild without deploying
- Keep secrets in GitHub Actions for auto-deployment
- Monitor usage at https://fly.io/dashboard
- Use `fly billing` to check spending
- Set up alerts for resource limits

---

**Deployed? Great!** 🎉

Now you can:
- Upload PDFs via the frontend
- Ask questions about your documents
- Share the public URL with others
- Scale up if needed (still free tier!)

**Cost**: $0 forever (on free tier limits)

