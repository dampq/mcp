"""Local document indexing and source-grounded retrieval for the MCP assistant."""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DOCUMENTS = Path(os.getenv('RESEARCH_DOCS_DIR', str(BASE / 'documents'))).resolve()
DB_PATH = Path(os.getenv('RESEARCH_DB_PATH', str(BASE / 'research.db'))).resolve()
ALLOWED = {'.pdf', '.docx', '.txt', '.md'}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, path TEXT UNIQUE, title TEXT, modified REAL)')
    connection.execute('CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE, locator TEXT, body TEXT)')
    connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(body, content='chunks', content_rowid='id')")
    connection.executescript('''
      CREATE TRIGGER IF NOT EXISTS chunks_insert AFTER INSERT ON chunks BEGIN
        INSERT INTO chunks_fts(rowid,body) VALUES(new.id,new.body);
      END;
      CREATE TRIGGER IF NOT EXISTS chunks_delete AFTER DELETE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts,rowid,body) VALUES('delete',old.id,old.body);
      END;
      CREATE TRIGGER IF NOT EXISTS chunks_update AFTER UPDATE ON chunks BEGIN
        INSERT INTO chunks_fts(chunks_fts,rowid,body) VALUES('delete',old.id,old.body);
        INSERT INTO chunks_fts(rowid,body) VALUES(new.id,new.body);
      END;
    ''')
    return connection


def extract_sections(path: Path):
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        import pymupdf
        with pymupdf.open(path) as pdf:
            for index, page in enumerate(pdf, 1):
                yield f'page {index}', page.get_text('text', sort=True)
    elif suffix == '.docx':
        from docx import Document
        doc = Document(str(path))
        elements = [p.text for p in doc.paragraphs if p.text.strip()]
        for table in doc.tables:
            for row in table.rows:
                elements.append(' | '.join(cell.text for cell in row.cells))
        yield 'document', '\n'.join(elements)
    elif suffix in ('.txt', '.md'):
        yield 'document', path.read_text(encoding='utf-8-sig', errors='replace')
    else:
        raise ValueError(f'Unsupported file type: {suffix}')


def split_text(text, max_chars=1100, overlap=150):
    text = re.sub(r'[ \t]+', ' ', text).strip()
    if not text:
        return
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            breakpoint = text.rfind(' ', start + max_chars // 2, end)
            if breakpoint > start:
                end = breakpoint
        piece = text[start:end].strip()
        if piece:
            yield piece
        if end == len(text):
            break
        start = max(start + 1, end - overlap)


def _safe_document_path(name: str) -> Path:
    """Restrict file access to the configured documents folder."""
    candidate = (DOCUMENTS / name).resolve()
    if not candidate.is_relative_to(DOCUMENTS) or not candidate.is_file():
        raise ValueError('File must exist inside the documents folder')
    if candidate.suffix.lower() not in ALLOWED:
        raise ValueError('Only PDF, DOCX, TXT, and MD are supported')
    return candidate


def index_document(name: str) -> dict:
    path = _safe_document_path(name)
    modified = path.stat().st_mtime
    with connect() as conn:
        old = conn.execute('SELECT id, modified FROM documents WHERE path=?', (str(path),)).fetchone()
        if old and old['modified'] == modified:
            count = conn.execute('SELECT count(*) FROM chunks WHERE document_id=?', (old['id'],)).fetchone()[0]
            return {'file': path.name, 'status': 'unchanged', 'chunks': count}
        sections = []
        for locator, text in extract_sections(path):
            sections.extend((locator, chunk) for chunk in split_text(text))
        if not sections:
            return {'file': path.name, 'status': 'no readable text (scanned PDFs need OCR)', 'chunks': 0}
        if old:
            conn.execute('DELETE FROM chunks WHERE document_id=?', (old['id'],))
            conn.execute('UPDATE documents SET title=?, modified=? WHERE id=?', (path.name, modified, old['id']))
            doc_id = old['id']
        else:
            doc_id = conn.execute('INSERT INTO documents(path,title,modified) VALUES(?,?,?)',
                                  (str(path), path.name, modified)).lastrowid
        conn.executemany('INSERT INTO chunks(document_id,locator,body) VALUES(?,?,?)',
                         [(doc_id, locator, chunk) for locator, chunk in sections])
    return {'file': path.name, 'status': 'indexed', 'chunks': len(sections)}


def index_all() -> list[dict]:
    DOCUMENTS.mkdir(parents=True, exist_ok=True)
    results = []
    for path in sorted(DOCUMENTS.rglob('*')):
        if path.is_file() and path.suffix.lower() in ALLOWED:
            try:
                results.append(index_document(str(path.relative_to(DOCUMENTS))))
            except Exception as exc:
                results.append({'file': str(path.name), 'status': f'error: {exc}', 'chunks': 0})
    return results


def list_documents() -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute('''
          SELECT d.title AS file, COUNT(c.id) AS chunks FROM documents d
          LEFT JOIN chunks c ON c.document_id=d.id GROUP BY d.id ORDER BY d.title
        ''')]


def search_documents(query: str, limit: int = 5) -> list[dict]:
    words = re.findall(r'\w+', query, flags=re.UNICODE)
    if not words:
        return []
    # Quote terms to prevent user input from being treated as FTS operators.
    match = ' OR '.join('"' + word.replace('"', '""') + '"' for word in words[:20])
    limit = max(1, min(int(limit), 20))
    with connect() as conn:
        rows = conn.execute('''
          SELECT d.title AS file, c.locator, c.body AS excerpt,
                 bm25(chunks_fts) AS rank
          FROM chunks_fts JOIN chunks c ON chunks_fts.rowid = c.id
          JOIN documents d ON c.document_id = d.id
          WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?
        ''', (match, limit)).fetchall()
    return [{**dict(row), 'citation': f"[{row['file']} — {row['locator']}]"} for row in rows]


def answer_question(question: str, limit: int = 5) -> dict:
    """Extractive evidence-based response. An MCP host LLM can synthesize the answer."""
    hits = search_documents(question, limit)
    if not hits:
        return {'question': question, 'answer': 'No matching source text was found. Add documents and index them first.', 'sources': []}
    evidence = '\n\n'.join(f"{hit['citation']}\n{hit['excerpt']}" for hit in hits)
    return {
        'question': question,
        'answer': 'Retrieved source passages (the connected AI client should synthesize an answer using only these passages):\n\n' + evidence,
        'sources': [{k: h[k] for k in ('file', 'locator', 'citation')} for h in hits],
    }
