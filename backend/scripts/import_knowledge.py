"""Run from backend: python -m scripts.import_knowledge [--download-model]."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT.parent / ".env")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-model", action="store_true")
    args = parser.parse_args()
    from app.services.knowledge_embeddings import MODEL, cache_path
    if args.download_model:
        from fastembed import TextEmbedding
        TextEmbedding(model_name=MODEL, cache_dir=str(cache_path()), threads=2)
    from app.db.session import SessionLocal
    from app.services.knowledge_ingest import ingest
    records = json.loads((ROOT / "data/knowledge/chengdu.json").read_text(encoding="utf-8"))
    with SessionLocal() as db:
        print(json.dumps(ingest(db, records), ensure_ascii=False))


if __name__ == "__main__":
    main()
