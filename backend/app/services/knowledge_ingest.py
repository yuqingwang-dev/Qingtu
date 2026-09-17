"""Trusted, local manifest ingestion only. No user-controlled URL fetching."""
import hashlib
import json
from datetime import date
from urllib.parse import urlparse
from sqlalchemy import select, delete
from app.db.models import KnowledgeDocument, KnowledgeChunk
from app.services.knowledge_embeddings import MODEL, embed_documents

ALLOWED_HOSTS = {"www.panda.org.cn", "m.panda.org.cn", "wuhouci.net.cn", "www.cddfct.cn"}


def validate_manifest(records):
    keys = set()
    for doc in records:
        url = urlparse(doc["url"])
        if url.scheme != "https" or url.hostname not in ALLOWED_HOSTS or url.username or url.port:
            raise ValueError("Only reviewed official HTTPS source URLs are allowed")
        if doc["source_key"] in keys:
            raise ValueError("Duplicate source key")
        keys.add(doc["source_key"])
        reviewed, expires = date.fromisoformat(doc["reviewed_on"]), date.fromisoformat(doc["expires_on"])
        if reviewed > date.today() or expires <= reviewed:
            raise ValueError("Invalid source review dates")
        if not doc["aliases"] or not doc["chunks"] or len(doc["chunks"]) > 50:
            raise ValueError("Invalid source content")
        chunk_keys = set()
        for chunk in doc["chunks"]:
            if chunk["key"] in chunk_keys or not 5 <= len(chunk["content"]) <= 800:
                raise ValueError("Invalid or duplicate chunk")
            chunk_keys.add(chunk["key"])


def ingest(db, records, embed=embed_documents):
    validate_manifest(records)
    changed = skipped = 0
    for record in records:
        fingerprint = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        doc = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.source_key == record["source_key"]))
        if (doc and doc.content_hash == fingerprint
                and len(doc.chunks) == len(record["chunks"])
                and all(c.embedding_model == MODEL for c in doc.chunks)):
            skipped += 1
            continue
        vectors = embed([f'{record["poi_name"]} {c["topic"]}：{c["content"]}' for c in record["chunks"]])
        if len(vectors) != len(record["chunks"]):
            raise ValueError("Embedding count mismatch")
        if doc is None:
            doc = KnowledgeDocument(source_key=record["source_key"], version=1)
            db.add(doc)
        else:
            doc.version += 1
            db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
            db.expire(doc, ["chunks"])
        for key in ("title", "url", "city", "poi_name", "aliases", "reviewed_on", "expires_on"):
            setattr(doc, key, record[key])
        doc.content_hash = fingerprint
        db.flush()
        for chunk, vector in zip(record["chunks"], vectors):
            db.add(KnowledgeChunk(id=f'{record["source_key"]}:{chunk["key"]}', document_id=doc.id,
                                 topic=chunk["topic"], content=chunk["content"], embedding_model=MODEL,
                                 embedding_vec=vector))
        changed += 1
    db.commit()
    return {"changed": changed, "skipped": skipped}
