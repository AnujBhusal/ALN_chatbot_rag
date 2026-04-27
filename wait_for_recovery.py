#!/usr/bin/env python3
"""Wait for backend server to recover."""
import requests
import time

BASE_URL = "https://aln-chatbot-rag.onrender.com/health"
max_wait = 300  # 5 minutes
interval = 10

print("⏳ Waiting for backend to recover...")
start = time.time()

while time.time() - start < max_wait:
    try:
        r = requests.get(BASE_URL, timeout=5)
        elapsed = int(time.time() - start)
        print(f"   {elapsed}s: Status {r.status_code}")
        
        if r.status_code == 200:
            print(f"✅ Server recovered after {elapsed}s!")
            exit(0)
    except Exception as e:
        elapsed = int(time.time() - start)
        print(f"   {elapsed}s: Connection error - {type(e).__name__}")
    
    time.sleep(interval)

print("❌ Server did not recover within 5 minutes")
exit(1)
