"""
app.py
------
Streamlit frontend for the RAG Document Chatbot.
Talks to the FastAPI backend (backend/main.py) for document ingestion and Q&A.

Run directly with:  streamlit run app.py
Set BACKEND_URL env var if the API is not on http://localhost:8000
"""
import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="RAG Document Chatbot", page_icon="", layout="wide")

st.title("RAG Document Chatbot")
st.caption("Upload PDFs / DOCX / TXT files, then ask questions about their content.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "documents" not in st.session_state:
    st.session_state.documents = []

# --------------------------------------------------------------------------
# Sidebar: document upload + knowledge base management
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Knowledge Base")

    uploaded_file = st.file_uploader("Upload a document", type=["pdf", "docx", "txt", "md"])
    if uploaded_file is not None:
        if st.button("Add to knowledge base", use_container_width=True):
            with st.spinner(f"Processing {uploaded_file.name}..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
                try:
                    resp = requests.post(f"{BACKEND_URL}/upload", files=files, timeout=120)
                    if resp.status_code == 200:
                        data = resp.json()
                        st.session_state.documents.append(data["source"])
                        st.success(
                            f"Added '{data['source']}' — {data['num_chunks']} chunks "
                            f"from {data['num_pages']} page(s)."
                        )
                    else:
                        st.error(f"Upload failed: {resp.json().get('detail', resp.text)}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Could not reach backend at {BACKEND_URL}: {e}")

    st.divider()
    st.subheader("Documents in this session")
    if st.session_state.documents:
        for doc in st.session_state.documents:
            st.write(f"{doc}")
    else:
        st.write("No documents uploaded yet.")

    st.divider()
    if st.button("Clear knowledge base", use_container_width=True):
        try:
            requests.post(f"{BACKEND_URL}/reset", timeout=30)
            st.session_state.documents = []
            st.session_state.messages = []
            st.success("Knowledge base cleared.")
        except requests.exceptions.RequestException as e:
            st.error(f"Could not reach backend at {BACKEND_URL}: {e}")

    st.divider()
    k = st.slider("Chunks to retrieve (k)", min_value=1, max_value=10, value=4)
    st.caption(f"Backend: {BACKEND_URL}")

# --------------------------------------------------------------------------
# Main: chat interface
# --------------------------------------------------------------------------


def render_sources(sources):
    with st.expander("Sources"):
        for s in sources:
            page_info = f" (page {s['page'] + 1})" if s.get("page") is not None else ""
            st.markdown(f"**{s['source']}{page_info}**")
            st.caption(s["snippet"] + "...")


for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])

if prompt := st.chat_input("Ask a question about your documents..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if not st.session_state.documents:
            st.warning("Please upload a document first.")
        else:
            with st.spinner("Thinking..."):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/chat",
                        json={"question": prompt, "k": k},
                        timeout=120,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        st.markdown(data["answer"])
                        if data.get("sources"):
                            render_sources(data["sources"])
                        st.session_state.messages.append(
                            {
                                "role": "assistant",
                                "content": data["answer"],
                                "sources": data.get("sources", []),
                            }
                        )
                    else:
                        err = resp.json().get("detail", resp.text)
                        st.error(f"Error: {err}")
                except requests.exceptions.RequestException as e:
                    st.error(f"Could not reach backend at {BACKEND_URL}: {e}")
