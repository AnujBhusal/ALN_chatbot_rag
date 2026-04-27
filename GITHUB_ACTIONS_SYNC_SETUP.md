# Automated PDF Sync to Render - Setup Guide

## Overview

This system **automatically syncs PDFs** from `data/pdfs/` folder to the Render backend using GitHub Actions.

### How It Works

```
You commit PDFs to repo
         ↓
GitHub Actions triggered (schedule or manual)
         ↓
Python script runs:
  - Checks which PDFs are new
  - Uploads only new ones (no duplicates)
  - Retries on timeout (handles old errors)
  - Updates tracking file
         ↓
Render backend receives PDF
         ↓
Background processing ingests
         ↓
Backend ready to query
```

---

## Setup (2 Steps)

### Step 1: Get Render API Key (Already Done!)

Since your backend is on Render, just verify:
1. Go to https://dashboard.render.com/account/tokens
2. Create an API key if you haven't
3. **Note it down** (we'll use it in Step 2)

### Step 2: Add GitHub Secret

1. Go to your GitHub repo: https://github.com/AnujBhusal/ALN_chatbot_rag
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Name: `RENDER_API_KEY`
5. Value: Paste your Render API key
6. Click **Add secret**

✅ Done! GitHub Actions can now access your Render backend.

---

## Usage

### Automatic (Daily)
The workflow runs **automatically every day at 2 AM UTC**.

### Manual (On Demand)

1. Go to **Actions** tab in GitHub
2. Select **"Sync PDFs to Render Backend"** workflow
3. Click **Run workflow**
4. Choose:
   - **Branch**: `main`
   - **Force reupload**: `false` (or `true` to re-upload all)
5. Click **Run workflow**

✅ Workflow starts! Check logs for progress.

---

## How It Avoids Old Errors

### ✅ Server Crashes
- **Sequential uploads** (1 at a time, not all at once)
- **Extended timeout** (60s, learned from old failures)
- **Retry logic** (auto-retries on timeout)
- **Background processing** (backend processes async)

### ✅ Duplicates
- **Tracking file** (`.uploaded_pdfs.json`) remembers uploaded PDFs
- **File hash checking** (detects if PDF changed)
- **Only new PDFs uploaded** (skips already-done ones)

### ✅ Connection Issues
- **Retry 3 times** on connection error
- **10s wait between retries** (lets server recover)
- **Clear error messages** (logs failures for debugging)

---

## File Structure

```
Rag-Backend/
├── .github/
│   └── workflows/
│       └── sync-pdfs.yml          ← GitHub Actions workflow
├── scripts/
│   └── sync_pdfs_to_render.py     ← Upload script
├── data/
│   └── pdfs/                      ← Your PDFs go here
│       ├── Assessment Brief.pdf
│       ├── General_Document.pdf
│       └── ... (7 PDFs total)
└── .uploaded_pdfs.json            ← Tracking file (auto-updated)
```

---

## Tracking File

The `.uploaded_pdfs.json` file tracks uploads:

```json
{
  "uploaded": {
    "Assessment Brief 2024-5 CMP6230 Data Management and MLops.pdf": {
      "hash": "abc123...",
      "uploaded_at": "2024-04-27 14:30:45",
      "size_bytes": 562412
    }
  },
  "failed": {
    "SomeFile.pdf": {
      "last_error": "2024-04-27 02:00:00",
      "retry_count": 2
    }
  },
  "last_sync": "2024-04-27 14:35:20",
  "total_uploaded": 7
}
```

This is **auto-committed back to repo** after each sync.

---

## Example Workflow Run

### Check Progress

1. Go to **Actions** tab
2. Click the latest "Sync PDFs to Render Backend" run
3. See detailed logs:

```
✅ PDF SYNC TO RENDER BACKEND
📚 Found 7 total PDFs

[1/7] 📄 Uploading Assessment Brief 2024-5...pdf... ✅ Success (ID: 35)

[2/7] 📄 Uploading General_Document.pdf... ✅ Success (ID: 36)

[3/7] 📄 Uploading Donor_Proposal.pdf... ✅ Success (ID: 37)

[4/7] 📄 Uploading Meeting_Notes.pdf... ✅ Success (ID: 38)

[5/7] 📄 Uploading Internal_Policy.pdf... ✅ Success (ID: 39)

[6/7] 📄 Uploading Integrity_Icon.pdf... ✅ Success (ID: 40)

[7/7] 📄 Uploading Governance_Weekly.pdf... ✅ Success (ID: 41)

📊 UPLOAD SUMMARY
✅ Successful: 7/7
   ✅ Assessment Brief...
   ✅ General_Document.pdf
   ... etc

⏳ PDFs processing in background (~1-2 min per file)
```

---

## Local Testing

You can also run the sync script locally for testing:

```bash
# Install dependencies
pip install requests

# Test sync (without GitHub Actions)
cd Rag-Backend
python scripts/sync_pdfs_to_render.py
```

This will:
1. Check `data/pdfs/` for new PDFs
2. Upload to Render backend
3. Update `.uploaded_pdfs.json`
4. Show progress and errors

---

## Workflow

### If New PDF Added

1. Add PDF to `data/pdfs/` folder locally
2. Commit and push to GitHub:
   ```bash
   git add data/pdfs/NewFile.pdf
   git commit -m "Add new PDF: NewFile"
   git push
   ```
3. **Next day at 2 AM** → Workflow runs automatically
4. **Or manually** → Go to Actions → Run workflow
5. PDF uploads to Render backend
6. `.uploaded_pdfs.json` updated
7. Query your PDF immediately after!

### If PDF Changed

1. Replace PDF in `data/pdfs/`
2. Commit and push
3. Workflow detects hash changed
4. Re-uploads the PDF
5. New version available

### If Sync Fails

1. Check GitHub Actions logs
2. See exactly which PDF failed and why
3. Click **"Re-run failed jobs"**
4. Script automatically retries

---

## Security Notes

### API Key Security
- Render API key stored as **GitHub Secret** (not in code/logs)
- Only visible in workflow with `env.RENDER_API_KEY`
- Safe to commit everything else to public repo

### Tracking File
- `.uploaded_pdfs.json` is public (safe - just metadata)
- Doesn't contain API keys or sensitive data
- Helps avoid duplicate uploads

---

## Advantages

✅ **Fully automated** - No manual uploads needed  
✅ **Scheduled** - Runs daily or on-demand  
✅ **No server crashes** - Sequential + retry logic  
✅ **Duplicate-free** - Tracking prevents re-uploads  
✅ **Error handling** - Timeouts and connection issues retried  
✅ **History** - All uploads logged in GitHub Actions  
✅ **Free** - GitHub Actions free for public repos  
✅ **Version control** - PDFs in git, history preserved  

---

## Troubleshooting

### Workflow Not Triggering?

1. Check GitHub Actions is enabled: **Settings** → **Actions**
2. Verify secret added: **Settings** → **Secrets and variables** → **Actions**
3. Manual trigger: **Actions** tab → **Run workflow**

### "Failed to upload" Errors?

1. Check Render API key is correct
2. Verify backend URL is correct (should be auto-detected)
3. Check PDF files are in `data/pdfs/`
4. Check Render logs: https://dashboard.render.com → aln-chatbot-rag → Logs

### PDFs Not Appearing in Backend?

1. **Wait 2-3 minutes** for background processing
2. Query with mode: `"documents"`
3. Check `.uploaded_pdfs.json` shows upload succeeded
4. Check Render logs for embedding errors

### How to Force Re-upload All PDFs?

1. Go to **Actions** tab
2. Run workflow with **"Force reupload" = true**
3. All PDFs uploaded again, tracking updated

---

## Summary

### What You Have Now

1. **GitHub Actions workflow** that runs daily + on-demand
2. **Python script** that uploads PDFs with retry logic
3. **Tracking file** that prevents duplicates
4. **Automated pipeline** from commit to live backend

### Workflow

1. **Local**: Add PDF to `data/pdfs/`, commit and push
2. **GitHub**: Actions workflow runs (automatically daily or manual)
3. **Sync**: Script uploads new PDFs only (no duplicates)
4. **Render**: Backend receives PDF, processes in background
5. **Query**: API ready to answer questions about PDF

### No More Manual Uploads! 🎉

All PDFs sync automatically. Just add to folder and push to GitHub.
