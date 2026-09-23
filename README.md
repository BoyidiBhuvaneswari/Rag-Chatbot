# RAG Document Chatbot

A Retrieval-Augmented Generation (RAG) chatbot that lets users upload their own documents (PDF, DOCX, TXT, Markdown) and ask questions about them. Answers are grounded in the actual uploaded content, and every answer is accompanied by the source chunks it was derived from.

## Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit 1.39 |
| Backend API | FastAPI 0.115, Uvicorn 0.30 |
| RAG framework | LangChain 1.x (community, text-splitters, huggingface, groq integrations) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (runs locally, no API cost) |
| Vector store | ChromaDB 0.5 (persistent, local) |
| Language model | Groq-hosted model (configurable via `CHAT_MODEL`, default `openai/gpt-oss-120b`) |
| Document parsing | pypdf (PDF), docx2txt (DOCX), LangChain TextLoader (TXT/MD) |

## Architecture

```
                 +---------------------+
                 |   Streamlit UI      |   port 8501 (dev) / 7860 (Docker)
                 |   frontend/app.py   |
                 +---------+-----------+
                           |  HTTP (requests)
                           v
                 +---------------------+
                 |   FastAPI backend   |   port 8000
                 |   backend/main.py   |
                 |  /upload /chat      |
                 |  /reset /health     |
                 +---------+-----------+
                           |
                           v
                 +---------------------+
                 |   RAG engine        |
                 |  backend/rag_engine |
                 +---------+-----------+
                           |
        +------------------+-------------------+
        |                  |                   |
        v                  v                   v
+-------------+   +---------------+   +---------------+
| Document    |   | Embeddings    |   | Groq LLM      |
| loaders +   |   | MiniLM-L6-v2  |   | (chat model)  |
| chunker     |   +-------+-------+   +---------------+
+-------------+           |
                          v
                 +---------------------+
                 |  ChromaDB (local    |
                 |  persistent store)  |
                 +---------------------+
```

## How It Works

1. **Ingestion.** The user uploads a document in the Streamlit sidebar. The FastAPI `/upload` endpoint saves it to a temporary file and hands it to the RAG engine.
2. **Loading and chunking.** The appropriate LangChain loader parses the file; `RecursiveCharacterTextSplitter` breaks the text into overlapping chunks (default 1000 characters with 150 characters of overlap).
3. **Embedding and storage.** Each chunk is embedded locally with `all-MiniLM-L6-v2` and written to a persistent ChromaDB collection (`rag_documents`).
4. **Retrieval.** When a question arrives at `/chat`, the question is embedded and the `k` most similar chunks are retrieved from Chroma.
5. **Generation.** The retrieved chunks are inserted into a prompt that instructs the model to answer only from the provided context and to state when it does not know. The prompt is sent to the Groq-hosted chat model.
6. **Response.** The answer plus the list of source chunks (document name, page number, snippet) are returned and rendered in the chat.

## Project Structure

```
rag-chatbot/
├── backend/
│   ├── main.py            FastAPI application (upload, chat, reset, health)
│   └── rag_engine.py      Chunking, embeddings, vector store, QA logic
├── frontend/
│   └── app.py             Streamlit chat interface
├── tests/
│   └── smoke_document.txt Sample document for smoke testing
├── requirements.txt       Combined backend and frontend dependencies
├── Dockerfile             Single-container image running both services
├── start.sh               Container entrypoint (backend then frontend)
├── .env.example           Template for environment configuration
├── .gitignore
├── README.md              This file
└── docs/
    └── PROJECT_DOCUMENTATION.pdf   Full project documentation (PDF)
```

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check; returns `{"status": "ok"}` |
| POST | `/upload` | Multipart file upload; ingests the document into the vector store |
| POST | `/chat` | JSON body `{"question": str, "k": int}`; returns `{"answer", "sources"}` |
| POST | `/reset` | Deletes the entire knowledge base |
| GET | `/docs` | Interactive OpenAPI documentation (Swagger UI) |

## Local Setup and Running

### Prerequisites

- Python 3.10 or newer
- A Groq API key from https://console.groq.com/keys

### Installation

```bash
cd rag-chatbot
python -m venv venv
venv\Scripts\activate          # Windows (PowerShell: .\venv\Scripts\Activate.ps1)
pip install -r requirements.txt
copy .env.example .env         # then edit .env and set GROQ_API_KEY
```

### Run the backend (terminal 1)

```powershell
cd backend
uvicorn main:app --port 8000
```

Verify at http://localhost:8000/health. Interactive API docs: http://localhost:8000/docs

### Run the frontend (terminal 2)

```powershell
cd frontend
streamlit run app.py
```

Open http://localhost:8501, upload a document in the sidebar, click "Add to knowledge base", then ask questions in the chat box.

## Configuration Reference

All settings are read from environment variables or the `.env` file.

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | none (required) | API key for the Groq inference service |
| `CHAT_MODEL` | `openai/gpt-oss-120b` | Groq chat model identifier |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Local embedding model |
| `CHUNK_SIZE` | `1000` | Maximum characters per chunk |
| `CHUNK_OVERLAP` | `150` | Overlapping characters between chunks |
| `CHROMA_DIR` | `chroma_db` | Directory for the persistent vector store |
| `BACKEND_URL` | `http://localhost:8000` | Used by the frontend to reach the API |
| `HF_HOME` | `.hf-cache` | Cache location for Hugging Face model downloads |

## Docker

The included `Dockerfile` builds a single container that runs the FastAPI backend on port 8000 internally and exposes the Streamlit UI on port 7860.

```bash
docker build -t rag-chatbot .
docker run -p 7860:7860 --env-file .env rag-chatbot
```

Open http://localhost:7860.

## Deployment

### Option A: Hugging Face Spaces (recommended, free)

1. Create a new Space at https://huggingface.co/new-space with SDK set to **Docker**.
2. Push this repository's files to the Space's git repository (the `Dockerfile`, `start.sh`, `requirements.txt`, `backend/`, `frontend/` must be present).
3. In the Space settings, under **Variables and secrets**, add `GROQ_API_KEY` with your real key. Never commit the key itself.
4. The Space builds the image automatically and serves the app on port 7860. The YAML header at the top of the Hugging Face variant of the README (`sdk: docker`, `app_port: 7860`) must be preserved.

Note: the container filesystem is ephemeral. If the Space restarts, the ChromaDB contents are cleared and documents must be re-uploaded. For persistence, mount a volume or switch to a managed vector database such as Pinecone.

### Option B: Render / Railway (single web service)

1. Create a new Web Service pointing at this repository.
2. Runtime: Docker (the provided `Dockerfile` works as-is).
3. Set the environment variable `GROQ_API_KEY`.
4. Expose port 7860 as the public port.

### Option C: Any VPS with Docker

```bash
git clone <your-repo-url>
cd rag-chatbot
cp .env.example .env && nano .env    # set GROQ_API_KEY
docker build -t rag-chatbot .
docker run -d -p 80:7860 --env-file .env --restart unless-stopped rag-chatbot
```

## Design Notes and Limitations

- **Model selection.** The chat model is fully configurable via `CHAT_MODEL`. The code never hardcodes a model identifier; if a Groq model becomes unavailable on your account, update `CHAT_MODEL` in `.env`. Available models can be listed via the Groq API `/models` endpoint.
- **Shared knowledge base.** All uploaded documents share a single Chroma collection. For multi-user isolation, namespace the collection by user or session id in `rag_engine.py`.
- **Ephemeral storage in containers.** See the deployment notes above.
- **Scanned PDFs.** Documents that contain images rather than text require an OCR preprocessing step (for example `pytesseract`), which is not included.
- **Retrieval quality.** Answer quality depends on chunking parameters and the embedding model; tune `CHUNK_SIZE`, `CHUNK_OVERLAP`, and `k` for your document types.

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| Frontend shows "Could not reach backend" | Backend not running, or `BACKEND_URL` points to the wrong host or port |
| Startup warning about `GROQ_API_KEY` | Key missing from `.env` or the deployment secrets |
| 404 `model_not_found` from Groq | The configured `CHAT_MODEL` is not available on your account; pick a model listed by the `/models` endpoint |
| Slow first question | Embedding model loads lazily on first use; later requests are faster |
| Garbled PDF text | The PDF is a scanned image; OCR preprocessing is required |