# MCP-Enabled Research Document Assistant

A local-first MCP (Model Context Protocol) server that indexes research **PDF, DOCX, Markdown, and TXT** files, searches them using SQLite FTS5, and returns source-labeled excerpts for an AI client to synthesize. No paid API or embeddings are required for retrieval.

## Setup (Windows PowerShell)

```powershell
cd mcp_research_assistant
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
mkdir documents
copy sample_docs\example_research.md documents\
python cli.py index
python cli.py search "frame extraction"
python cli.py ask "What does FPS mean?"
```

On macOS/Linux: replace venv activation with `source .venv/bin/activate` and `copy` with `cp`.

## Connect an MCP-compatible desktop/IDE client

Use **stdio** and configure a server process (replace paths with the absolute paths on your computer):

```json
{
  "mcpServers": {
    "research-documents": {
      "command": "C:\\full\\path\\mcp_research_assistant\\.venv\\Scripts\\python.exe",
      "args": ["C:\\full\\path\\mcp_research_assistant\\server.py"]
    }
  }
}
```

Client configuration filenames and schemas differ; consult your particular MCP client. Restart the client after updating its configuration.

## Available MCP tools

- `index_research_documents` — scan and index local files
- `index_research_file` — index a specific file inside `documents/`
- `list_research_documents` — list indexed files
- `search_research_documents` — return ranked excerpts with source labels
- `ask_research_documents` — provide research evidence for the client's language model to answer with citations

## File organization

```text
mcp_research_assistant/
  server.py
  research_core.py
  cli.py
  requirements.txt
  documents/              # put your own PDFs, DOCX, MD, TXT here
  sample_docs/
  tests/
```

## Notes / limitations

- This is a **local proof of concept**, not a multi-user/cloud service.
- Search is **keyword-based** (SQLite FTS5 BM25), not semantic embeddings. Synonyms may be missed.
- `ask_research_documents` returns quoted evidence; it does not itself call a cloud LLM. The MCP host AI client can use the evidence to write a grounded answer.
- Scanned/image-only PDFs require OCR (not included).
- PDF citations use page numbers; DOCX/TXT/MD citations identify the document (not a Word page number).
- Files are restricted to the configured documents directory, but a locally connected MCP client may read documents that the OS account can access in that directory. Do not add confidential files unless you trust the MCP host.
- File names should be unique within your document collection for unambiguous citations.
- An optional `RESEARCH_DOCS_DIR` environment variable can set the document directory and `RESEARCH_DB_PATH` can set the SQLite database.
- If you edit/remove files, re-index. Removed files are not automatically purged from the index in this starter version.

## Run tests

```bash
python -m unittest discover -s tests -v
```

Official MCP SDK (v2): https://github.com/modelcontextprotocol/python-sdk
