#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

def test_query(query):
    url = "https://aln-chatbot-rag.onrender.com/api/chat/query"
    payload = {
        "session_id": "test-123",
        "query": query,
        "mode": "general",
        "role": "staff"
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read())
            answer = data.get("answer", "")
            sources = data.get("sources", [])
            
            print(f"\n📝 Query: {query}")
            print(f"   Answer length: {len(answer)} chars")
            print(f"   Sources: {len(sources)}")
            
            if "Not available" in answer:
                print("   ❌ Not available")
            else:
                print("   ✅ Data found")
                if "Ram Bahadur" in answer or "award" in answer.lower():
                    print(f"   Preview: {answer[:150]}...")
    except Exception as e:
        print(f"   ❌ Error: {e}")

# Test multiple queries
queries = [
    "What are ALN awards?",
    "Who won ALN awards in 2020?",
    "List ALN nominees",
    "What documents do you have?",
    "Tell me about awards"
]

for q in queries:
    test_query(q)
