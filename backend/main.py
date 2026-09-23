"""
main.py
-------
FastAPI backend for the RAG Document Chatbot.

Endpoints:
    GET  /health   - health check
    POST /upload   - upload a document (pdf/docx/txt/md) to ingest into the vector store
    POST /chat     - ask a question against the ingested documents
    POST /reset    - clear the entire knowledge base

Run directly with:  uvicorn main:app --reload --port 8000
"""
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from rag_engine import ingest_document, ask_question, reset_knowledge_base

if not os.getenv("GROQ_API_KEY"):
    print("WARNING: GROQ_API_KEY is not set. Add it to your .env file or environment variables.")

app = FastAPI(title="RAG Document Chatbot API", version="1.0.0")

# Allow the Streamlit frontend (or any client) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class ChatRequest(BaseModel):
    question: str
    k: int = 4


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = ingest_document(tmp_path, source_name=file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process document: {e}")
    finally:
        os.unlink(tmp_path)

    return {"status": "success", **result}


@app.post("/chat")
def chat(req: ChatRequest):
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        result = ask_question(req.question, k=req.k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to answer question: {e}")
    return result


@app.post("/reset")
def reset():
    reset_knowledge_base()
    return {"status": "knowledge base cleared"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
