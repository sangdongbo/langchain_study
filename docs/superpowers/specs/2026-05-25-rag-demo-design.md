# Streamlit RAG Demo Design

## Goal

Create an isolated `rag_demo/` Streamlit app where users upload local `.txt` or `.md` files, persist chunks into a local Chroma vector store, search those chunks, and ask DeepSeek for an answer using retrieved context.

## Scope

- Add a new independent demo directory, leaving the existing Streamlit assistants unchanged.
- Use `.env` model settings already present in the project.
- Persist vectors under `rag_demo/chroma_db/`.
- Avoid any database commands, migrations, or destructive operations.

## Architecture

- `rag_demo/rag_chain.py` owns document conversion, splitting, Chroma persistence, retriever creation, LCEL chain construction, and logging helpers.
- `rag_demo/app.py` owns the Streamlit page, sidebar upload/index controls, right-side search/chat flow, and display styling.
- `rag_demo/README.md` documents setup, environment variables, and launch command.
- `tests/test_rag_demo.py` covers pure helpers that do not touch Chroma or call a model.

## Data Flow

1. User uploads one or more `.txt` or `.md` files in the sidebar.
2. The app decodes each file, converts it into LangChain `Document` objects, splits into chunks, and writes chunks to Chroma.
3. User enters a question on the right side.
4. The app retrieves top-k similar chunks from Chroma.
5. The LCEL chain formats retrieved context into a prompt, calls DeepSeek through OpenAI-compatible configuration, and parses text output.
6. The UI shows the answer, source snippets, and timestamped logs.

## Error Handling

- Empty uploads are skipped with a log entry.
- Unsupported suffixes are rejected in the UI by Streamlit file type filters.
- Missing API key errors are surfaced in the page instead of crashing.
- Searching before indexing shows a friendly warning.

## Verification

- Use `python -m unittest tests.test_rag_demo` for pure helper tests.
- Use `python -m py_compile rag_demo/app.py rag_demo/rag_chain.py` for syntax verification.
- Do not run `streamlit run` as a blocking command in automated verification.
