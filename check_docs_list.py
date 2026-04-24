import requests

BACKEND_URL = "https://aln-chatbot-rag.onrender.com/api/chat/documents"

def check_docs():
    response = requests.get(BACKEND_URL)
    if response.status_code == 200:
        docs = response.json()
        print(f"Found {len(docs)} documents:")
        for d in docs:
            print(f" - {d['title']} (ID: {d['id']}, Chunks: {d.get('chunk_count', 'N/A')})")
    else:
        print(f"Failed to fetch documents: {response.status_code}")

if __name__ == "__main__":
    check_docs()
