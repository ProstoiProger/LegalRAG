# Legal RAG Chatbot

This project was developed during the **NIRS competition** — a research competition focused on building practical AI systems.

Legal RAG is a **Retrieval-Augmented Generation (RAG)** chatbot that answers legal questions in **Kazakh** using the legislation of the Republic of Kazakhstan. It retrieves relevant legal text and generates formal legal conclusions based only on the provided context.

---

## Pipeline

End-to-end flow from user query to answer:

1. **Request** — Client sends a question via `POST /api/chat` (optionally with `chat_id` for conversation continuity).
2. **Chat state** — New chat is created if no/invalid `chat_id`; last 10 turns are used as conversation history.
3. **Hybrid retrieval** — Query is run against:
   - **Sparse (BM25)** — Elasticsearch full-text search on `text` → top candidates with `doc_id`, `chunk_id`, `text`.
   - **Dense** — Query encoded with BGE-M3 (`"query: " + question`), Qdrant vector search → same fields.
   - **Fusion** — Results merged by `(doc_id, chunk_id)`; sparse and dense scores normalized (min–max); `final_score = α × sparse_n + (1−α) × dense_n`; top‑k chunks selected (default `top_k=10`, `α=0.4`).
4. **Prompt** — System prompt (Kazakh legal assistant) + optional history + user message: `"КОНТЕКСТ:\n{context}\n\nСҰРАҚ:\n{query}"`.
5. **LLM** — OpenAI Chat Completions (e.g. `gpt-4.1`), temperature 0.
6. **Response** — Assistant reply is stored in the chat and returned as `{ answer, chat_id }`.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Frontend — frontend/                                            │
│  Vanilla JS + HTML + CSS; chat UI, list chats, send message      │
│  (config.js: API_BASE → backend URL)                             │
└─────────────────────────────────────────────────────────────────┘
                                    │ HTTP (fetch)
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  API layer (FastAPI) — main.py                                   │
│  • CORS, Pydantic models                                         │
│  • In-memory chat store (chats)                                  │
│  • /api/chat, /api/chats, /api/chats/{id}, DELETE /api/chats/{id}│
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│  RAG engine — engine.py                                          │
│  • get_legal_answer(query, history)                              │
│  • retrieve_hybrid_context() → prompt build → OpenAI             │
└─────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│  Elasticsearch    │   │  Qdrant            │   │  OpenAI           │
│  (sparse / BM25)  │   │  (dense vectors)   │   │  (Chat Completions)│
└───────────────────┘   └───────────────────┘   └───────────────────┘
            │                       │
            └───────────┬───────────┘
                        ▼
            ┌───────────────────────┐
            │  SentenceTransformer  │
            │  BAAI/bge-m3 (query)  │
            └───────────────────────┘
```

- **Configuration** — `config.py` loads `.env` from the project root and exposes server, OpenAI, Qdrant, Elasticsearch, and RAG parameters.

---

## Components

| Component | Role | Implementation |
|-----------|------|----------------|
| **Frontend** | Chat UI; list chats, send messages, switch conversations | Vanilla JS (`app.js`), HTML, CSS; `config.js` for `API_BASE`; calls `/api/chat`, `/api/chats`, `/api/chats/{id}` |
| **RAG** | Answer only from retrieved context; formal Kazakh legal style | System prompt in `engine.py` + context in user message; no hallucination beyond context |
| **Sparse retrieval** | Keyword / BM25 search | Elasticsearch index `ES_INDEX` (default `bm25`), field `text` |
| **Dense retrieval** | Semantic similarity | Qdrant collection `COLLECTION_NAME` (default `dense_structured_bge_m3_v1`), BGE-M3 vectors |
| **Embedding** | Query encoding | `SentenceTransformer("BAAI/bge-m3")`, prefix `"query: "`, normalized |
| **Hybrid fusion** | Combine sparse + dense | Min–max normalization per score type; weighted sum with `ALPHA` (default 0.4); top‑k by `final_score` |
| **LLM** | Final answer | OpenAI Chat API (`OPENAI_MODEL`, default `gpt-4.1`), temperature 0 |

---

## Project structure

```
LegalRAG/
├── .env                 # Environment variables (not in repo)
├── README.md            # This file
├── frontend/            # Web UI (vanilla JS)
│   └── src/
│       ├── index.html   # Entry page
│       ├── app.js       # Chat logic, API calls (/api/chat, /api/chats)
│       ├── config.js    # API_BASE (backend URL)
│       └── style.css    # Styles
└── backend/
    ├── config.py        # Loads .env; PORT, OpenAI, Qdrant, ES, RAG params
    ├── engine.py        # Hybrid retrieval + prompt + OpenAI (RAG logic)
    ├── main.py          # FastAPI app, chat endpoints, in-memory chats
    └── requirements.txt # Python dependencies
```

---

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Send `{ "query": "...", "chat_id": "..."? }` → `{ "answer": "...", "chat_id": "..." }` |
| `GET`  | `/api/chats` | List chats: `id`, `title`, `updated`, `message_count` |
| `GET`  | `/api/chats/{chat_id}` | Get one chat (messages, metadata) |
| `DELETE` | `/api/chats/{chat_id}` | Delete a chat |

---

## Setup

1. **Dependencies** (from `backend/`):
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Environment** — Create `.env` in the **project root** (parent of `backend/`):

   | Variable | Description | Default |
   |----------|-------------|---------|
   | `PORT` | Server port | `8000` |
   | `OPENAI_API_KEY` | OpenAI API key | — |
   | `OPENAI_MODEL` | Chat model | `gpt-4.1` |
   | `QDRANT_URL` | Qdrant server URL | — |
   | `QDRANT_API_KEY` | Qdrant API key | — |
   | `ELASTICSEARCH_URL` | Elasticsearch URL | — |
   | `ES_INDEX` | Elasticsearch index name | `bm25` |
   | `COLLECTION_NAME` | Qdrant collection name | `dense_structured_bge_m3_v1` |
   | `ALPHA` | Sparse weight in hybrid (0–1) | `0.4` |

3. **Run** (from `backend/`):
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   # or
   python main.py
   ```

---

## Dependencies

- **fastapi**, **uvicorn** — HTTP API  
- **pydantic** — Request/response models  
- **python-dotenv** — Load `.env`  
- **openai** — Chat Completions  
- **qdrant-client** — Vector search  
- **elasticsearch** — Sparse search  
- **sentence-transformers** — BGE-M3 embeddings  
- **pandas** — Hybrid score fusion  

---

*Developed for the NIRS research competition.*
