"""
rag_engine.py
--------------
Core RAG (Retrieval-Augmented Generation) logic:
  1. Load a document (PDF / DOCX / TXT)
  2. Split it into overlapping chunks
  3. Embed the chunks with OpenAI embeddings
  4. Store/retrieve vectors with ChromaDB (local, persistent, no extra signup needed)
  5. Run a Retrieval QA chain with an OpenAI chat model

To swap ChromaDB for Pinecone later, see the "PINECONE ALTERNATIVE" comment block
near get_vectorstore() below.
"""
import os
from pathlib import Path
from typing import Dict

from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_groq import ChatGroq
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import PromptTemplate

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables / .env)
# ---------------------------------------------------------------------------
CHROMA_DIR = os.getenv("CHROMA_DIR", "chroma_db")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
CHAT_MODEL = os.getenv("CHAT_MODEL", "llama-3.3-70b-versatile")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 1000))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))

os.makedirs(CHROMA_DIR, exist_ok=True)

_embeddings = None
_vectorstore = None


def get_embeddings() -> HuggingFaceEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return _embeddings


def get_vectorstore() -> Chroma:
    """Returns a persistent Chroma vector store instance (created once, reused)."""
    global _vectorstore
    if _vectorstore is None:
        _vectorstore = Chroma(
            collection_name="rag_documents",
            embedding_function=get_embeddings(),
            persist_directory=CHROMA_DIR,
        )
    return _vectorstore

    # -------------------------------------------------------------------
    # PINECONE ALTERNATIVE (optional)
    # -------------------------------------------------------------------
    # If you'd rather use Pinecone instead of local ChromaDB (e.g. for a
    # managed, scalable, multi-user deployment), replace the function body
    # above with something like:
    #
    #   from langchain_pinecone import PineconeVectorStore
    #   from pinecone import Pinecone
    #
    #   pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    #   index = pc.Index(os.environ["PINECONE_INDEX_NAME"])
    #   return PineconeVectorStore(index=index, embedding=get_embeddings())
    #
    # You'd also need to: `pip install langchain-pinecone pinecone-client`,
    # create an index in the Pinecone console (dimension must match your
    # embedding model, e.g. 1536 for text-embedding-3-small), and set
    # PINECONE_API_KEY / PINECONE_INDEX_NAME in your .env file.


def load_document(file_path: str):
    """Pick the right LangChain loader based on file extension."""
    ext = Path(file_path).suffix.lower()
    if ext == ".pdf":
        loader = PyPDFLoader(file_path)
    elif ext == ".docx":
        loader = Docx2txtLoader(file_path)
    elif ext in (".txt", ".md"):
        loader = TextLoader(file_path, encoding="utf-8")
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    return loader.load()


def ingest_document(file_path: str, source_name: str = None) -> Dict:
    """
    Loads a document, splits it into chunks, embeds and stores them in the vector DB.
    Returns metadata about the ingestion (page/chunk counts).
    """
    docs = load_document(file_path)
    source_name = source_name or Path(file_path).name

    for d in docs:
        d.metadata["source"] = source_name

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    vectordb = get_vectorstore()
    vectordb.add_documents(chunks)
    try:
        vectordb.persist()
    except Exception:
        # Newer Chroma versions auto-persist; ignore if persist() is a no-op/deprecated.
        pass

    return {"source": source_name, "num_pages": len(docs), "num_chunks": len(chunks)}


QA_PROMPT = PromptTemplate(
    template=(
        "You are a helpful assistant answering questions using ONLY the context below, "
        "which was extracted from documents the user uploaded. "
        "If the answer is not contained in the context, say you don't know instead of "
        "making something up.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}\n\n"
        "Answer (be concise, and mention which document the info came from when relevant):"
    ),
    input_variables=["context", "question"],
)


def ask_question(question: str, k: int = 4) -> Dict:
    """Runs the retrieval QA chain and returns the answer plus the source chunks used."""
    vectordb = get_vectorstore()
    source_documents = vectordb.similarity_search(question, k=k)
    if not source_documents:
        return {
            "answer": "I don't know because the knowledge base is empty.",
            "sources": [],
        }

    context = "\n\n".join(
        f"[Source: {doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
        for doc in source_documents
    )
    prompt = QA_PROMPT.format(context=context, question=question)
    llm = ChatGroq(model=CHAT_MODEL, temperature=0)
    response = llm.invoke(prompt)

    sources = []
    for doc in source_documents:
        sources.append(
            {
                "source": doc.metadata.get("source", "unknown"),
                "page": doc.metadata.get("page", None),
                "snippet": doc.page_content[:200],
            }
        )

    return {"answer": response.content, "sources": sources}


def reset_knowledge_base() -> None:
    """Deletes the Chroma collection so you can start fresh."""
    global _vectorstore
    vectordb = _vectorstore or get_vectorstore()
    try:
        vectordb.delete_collection()
    finally:
        _vectorstore = None
