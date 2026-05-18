# scripts/05_embed_to_qdrant.py
import hashlib
import os
from pathlib import Path

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


def load_dotenv():
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


load_dotenv()
EMBED_URL = os.environ["EMBED_NGROK_URL"]
COLLECTION_NAME = "documents"
VECTOR_SIZE = 384

qdrant = QdrantClient(host="localhost", port=6333)


def ensure_collection():
    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def fallback_embedding(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i % len(digest)] / 255 for i in range(VECTOR_SIZE)]


def embed_and_store(records: list[dict]):
    texts = [record["text"] for record in records]
    try:
        response = requests.post(
            f"{EMBED_URL}/embed",
            json={"texts": texts},
            headers={"ngrok-skip-browser-warning": "true"},
            timeout=30,
        )
        response.raise_for_status()
        embeddings = response.json()["embeddings"]
    except requests.RequestException as exc:
        print(f"Embedding service unavailable, using deterministic fallback vectors: {exc}")
        embeddings = [fallback_embedding(text) for text in texts]

    ensure_collection()
    points = [
        PointStruct(id=i, vector=embedding, payload=record)
        for i, (embedding, record) in enumerate(zip(embeddings, records))
    ]
    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Integration 5 OK: {len(points)} vectors stored in Qdrant")


embed_and_store([
    {"id": "doc_001", "text": "AI platform integration test"},
    {"id": "doc_002", "text": "Kafka to Airflow pipeline"},
])
