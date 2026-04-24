#!/usr/bin/env python3
"""Test the backend directly to see LLM initialization."""

import requests
import json

BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/chat/query"

test_payload = {
    "session_id": "test-session-123",
    "query": "Who is Shahrukh Khan?",
    "mode": "general",
    "role": "staff"
}

print("🧪 Testing LLM response from backend...\n")

try:
    response = requests.post(BACKEND_URL, json=test_payload, timeout=30)
    
    if response.status_code == 200:
        result = response.json()
        answer = result.get("answer", "")
        print(f"Status: ✅ {response.status_code}")
        print(f"Answer: {answer}\n")
        
        if "could not find enough" in answer.lower():
            print("❌ Still getting fallback response!")
            print("   This means Groq is not working or not initialized")
        else:
            print("✅ Got LLM response (not fallback)!")
    else:
        print(f"❌ Status: {response.status_code}")
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"❌ Error: {e}")
