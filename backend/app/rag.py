import os
import uuid
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding

from app.tracing import tracer
from app.metrics import record_embedding_version, EMBEDDING_VERSION_MISMATCH


QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "documents"
EMBEDDING_DIM = 384
EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_MODEL_VERSION = "v1"

record_embedding_version(EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_VERSION)

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Load the model from the local cache baked into the image at build time.
# local_files_only=True guarantees this never touches the network at
# runtime, regardless of NetworkPolicy or DNS/routing state in the cluster.
embedder = TextEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    cache_dir=os.environ.get("FASTEMBED_CACHE_PATH", "/opt/fastembed_cache"),
    local_files_only=True,
)


def ensure_collection():
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> List[str]:
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + chunk_size])
        start += chunk_size - overlap
    return [c.strip() for c in chunks if c.strip()]


def embed_and_store(text: str, filename: str) -> int:
    ensure_collection()
    chunks = chunk_text(text)
    vectors = list(embedder.embed(chunks))

    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=vector.tolist(),
            payload={
                "text": chunk,
                "filename": filename,
                "chunk_index": i,
                "embedding_model": EMBEDDING_MODEL_NAME,
                "embedding_model_version": EMBEDDING_MODEL_VERSION,
            },
        )
        for i, (chunk, vector) in enumerate(zip(chunks, vectors))
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)


def search_similar(query: str, top_k: int = 3) -> List[str]:
    with tracer.start_as_current_span("qdrant.search"):
        ensure_collection()
        query_vector = list(embedder.embed([query]))[0].tolist()
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k,
        )
        return [point.payload["text"] for point in results.points]

def check_embedding_version_drift():
    try:
        points, _ = client.scroll(collection_name=COLLECTION_NAME, limit=1)
        if points and points[0].payload.get("embedding_model_version") not in (None, EMBEDDING_MODEL_VERSION):
            EMBEDDING_VERSION_MISMATCH.set(1)
        else:
            EMBEDDING_VERSION_MISMATCH.set(0)
    except Exception:
        EMBEDDING_VERSION_MISMATCH.set(0)