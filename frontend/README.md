# ALN Chatbot Frontend

Minimal React + Tailwind UI for the ALN internal assistant.

## Run locally

1. Install dependencies:
   npm install

2. Start the dev server:
   npm run dev

3. Set the backend URL if needed:
   $env:VITE_API_BASE_URL="http://localhost:8000"

The UI calls `POST /chat/query` and expects the backend response shape:

{
  "answer": "...",
  "sources": [
    {
      "title": "...",
      "type": "...",
      "year": 2024,
      "snippet": "..."
    }
  ]
}
