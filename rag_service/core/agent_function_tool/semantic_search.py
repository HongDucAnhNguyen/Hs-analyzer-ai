import os
from llama_index.core import VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import AsyncQdrantClient

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hs_code_db")

SIMILARITY_THRESHOLD = 0.2

async def semantic_search(query: str, collection_name: str = None):
    collection = collection_name or QDRANT_COLLECTION
    aclient = AsyncQdrantClient(url=QDRANT_URL)
    vector_store = QdrantVectorStore(aclient=aclient, collection_name=collection)
    index = VectorStoreIndex.from_vector_store(vector_store)
    retriever = index.as_retriever(similarity_top_k=50, use_async=True)
    results = await retriever.aretrieve(query)
    filtered = [n for n in results if getattr(n, "score", 0) >= SIMILARITY_THRESHOLD]
    return filtered
