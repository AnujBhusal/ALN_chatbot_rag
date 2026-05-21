# 🚀 QUICK DEPLOYMENT COMMANDS

Copy-paste these commands in order to deploy the fix:

---

## Step 1: Review Changes (5 min)
```bash
# View the exact code changes
git diff app/api/ingest.py

# Or view the summary
cat FIX_IMPLEMENTATION_SUMMARY.md
```

---

## Step 2: Commit to Git (2 min)
```bash
cd c:\\Users\\shubh\\OneDrive\\Desktop\\ALNChatBot\\ALN_chatbot_rag

git add app/api/ingest.py

git commit -m \"🔥 Fix PDF duplication: Add Pinecone cleanup to delete/cleanup endpoints

FIXES:
- delete_document() endpoint now deletes vectors from Pinecone
- cleanup_duplicates() endpoint now deletes vectors from Pinecone
- Prevents orphaned vectors from causing duplicate search results

IMPACT:
- 3 PDFs will no longer show as 21+
- Deleted PDFs will not reappear in search results
- PostgreSQL and Pinecone stay in sync

TESTING:
- Can be tested locally with curl
- Post-deployment cleanup-duplicates is REQUIRED

FILES CHANGED:
- app/api/ingest.py: 25 lines added\"

git push origin main
```

---

## Step 3: Deploy to Production (5 min)

### Option A: Automatic (GitHub Actions)
```bash
# Just wait - it will auto-deploy
# Check status: https://github.com/your-repo/actions

# Or check logs:
git log --oneline
```

### Option B: Manual (Fly.io)
```bash
# Login if needed
flyctl auth login

# Deploy
flyctl deploy

# Wait for completion
flyctl status

# Watch logs
flyctl logs
```

---

## Step 4: Post-Deployment Cleanup (CRITICAL!) (3 min)

⚠️ **This step is REQUIRED to fix existing duplicates**

```bash
# Replace with your actual API URL
export API_URL=\"https://aln-chatbot-rag.onrender.com\"

# Run cleanup
curl -X DELETE $API_URL/api/ingest/cleanup-duplicates

# You should see response like:
# {
#   \"message\": \"Duplicate cleanup complete (database + Pinecone)\",
#   \"pinecone_sync_status\": \"complete\",
#   \"pinecone_cleaned\": 18
# }
```

---

## Step 5: Verification (5 min)

### Check Document Count
```bash
export API_URL=\"https://aln-chatbot-rag.onrender.com\"

# List documents - should show exactly 3
curl $API_URL/api/ingest/documents

# Expected response:
# {
#   \"total\": 3,
#   \"documents\": [
#     {\"id\": 1, \"title\": \"...\", ...},
#     {\"id\": 2, \"title\": \"...\", ...},
#     {\"id\": 3, \"title\": \"...\", ...}
#   ]
# }
```

### Check Logs
```bash
# Watch logs for Pinecone cleanup messages
flyctl logs | grep \"Deleted Pinecone vectors\"

# Should show messages like:
# ✅ Deleted Pinecone vectors for document 1
# ✅ Deleted Pinecone vectors for document 2
```

### Test Query (No Duplicates)
```bash
export API_URL=\"https://aln-chatbot-rag.onrender.com\"

curl -X POST $API_URL/api/chat/query \\
  -H \"Content-Type: application/json\" \\
  -d '{
    \"session_id\": \"test\",
    \"query\": \"governance\",
    \"mode\": \"general\"
  }'

# Check response - should have clean sources with no duplicate references
```

---

## Troubleshooting

### Issue: Cleanup returns \"partial\" sync status
```bash
# Run cleanup again
curl -X DELETE $API_URL/api/ingest/cleanup-duplicates

# Wait a moment for Pinecone to process
# Then run again if needed
```

### Issue: Still seeing duplicates
```bash
# 1. Check document count
curl $API_URL/api/ingest/documents

# 2. If count > 3, run cleanup again
curl -X DELETE $API_URL/api/ingest/cleanup-duplicates

# 3. Restart application
flyctl restart

# 4. Try query again
```

### Issue: Application won't start
```bash
# Check logs for errors
flyctl logs

# Rollback if needed
git revert HEAD
git push origin main
flyctl deploy
```

---

## All-In-One Script (Copy & Paste)

```bash
#!/bin/bash
set -e

echo \"🚀 PDF Duplication Fix - Full Deployment\"
echo \"=========================================\"
echo \"\"

# Step 1: Commit
echo \"Step 1: Committing changes...\"
git add app/api/ingest.py
git commit -m \"🔥 Fix PDF duplication: Add Pinecone cleanup\" || echo \"No changes to commit\"
git push origin main

echo \"✅ Changes committed\"
echo \"\"

# Step 2: Wait for deployment
echo \"Step 2: Waiting for deployment...\"
echo \"Check: https://github.com/your-repo/actions\"
read -p \"Press Enter after deployment completes (or wait 5 min)...\"

# Step 3: Cleanup
echo \"\"
echo \"Step 3: Running post-deployment cleanup...\"
API_URL=\"https://aln-chatbot-rag.onrender.com\"

CLEANUP_RESPONSE=$(curl -s -X DELETE $API_URL/api/ingest/cleanup-duplicates)
echo \"Cleanup response: $CLEANUP_RESPONSE\"

# Check if sync was successful
if echo $CLEANUP_RESPONSE | grep -q '\"complete\"'; then
    echo \"✅ Cleanup completed successfully\"
else
    echo \"⚠️  Cleanup may have failed - check response above\"
fi

echo \"\"

# Step 4: Verify
echo \"Step 4: Verifying results...\"
DOC_COUNT=$(curl -s $API_URL/api/ingest/documents | grep -o '\"total\":[0-9]*' | grep -o '[0-9]*')
echo \"Document count: $DOC_COUNT\"

if [ \"$DOC_COUNT\" -eq 3 ]; then
    echo \"✅ Verification successful!\"
    echo \"✅ 3 PDFs showing as 3 documents (not 21+)\"
    echo \"\"
    echo \"🎉 FIX COMPLETE!\"
else
    echo \"⚠️  Warning: Document count is $DOC_COUNT (expected 3)\"
    echo \"Run cleanup again or check logs\"
fi
```

---

## Quick Reference URLs

Once deployed, use these URLs:

```
API Base:              https://aln-chatbot-rag.onrender.com/api
Docs:                  https://aln-chatbot-rag.onrender.com/docs
List Documents:        https://aln-chatbot-rag.onrender.com/api/ingest/documents
Delete Document:       https://aln-chatbot-rag.onrender.com/api/ingest/documents/{id}
Cleanup Duplicates:    https://aln-chatbot-rag.onrender.com/api/ingest/cleanup-duplicates
Chat Query:            https://aln-chatbot-rag.onrender.com/api/chat/query
Logs:                  flyctl logs
Status:                flyctl status
```

---

## Success Checklist

After completing all steps:

- [ ] Code committed and pushed
- [ ] Deployment completed without errors
- [ ] Cleanup endpoint ran successfully
- [ ] Document count is 3
- [ ] Logs show \"Deleted Pinecone vectors\" messages
- [ ] Query test returns no duplicate references
- [ ] Cleanup sync_status = \"complete\"

---

## Time Estimate

- Review: 5 min
- Commit: 2 min  
- Deploy: 5 min
- Cleanup: 3 min
- Verify: 5 min
- **TOTAL: 20 minutes**

---

## One More Thing

If you're not comfortable with command line, just follow these steps visually:

1. Open GitHub Desktop or web interface
2. Commit the one changed file with the commit message
3. Go to Fly.io dashboard and wait for auto-deployment
4. Test with the Swagger docs at /docs endpoint
5. Use the cleanup-duplicates endpoint via Swagger UI
6. List documents and verify count = 3

All done! 🎉
