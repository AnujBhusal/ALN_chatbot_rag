import requests
import json

BACKEND_URL = "http://localhost:8000/api/chat/query" # I will test against production URL: "https://aln-chatbot-rag.onrender.com/api/chat/query"
BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/chat/query"

# We'll use a dummy session_id and role
data = {
    "session_id": "test_session_123",
    "query": "What is academic misconduct mentioned in the pdf?",
    "mode": "documents",
    "document_id": 13,
    "use_latest_document": True,
    "role": "staff"
}

headers = {"Content-Type": "application/json"}

print("Sending request...")
response = requests.post(BACKEND_URL, json=data, headers=headers)
print(f"Status: {response.status_code}")
try:
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(response.text)
