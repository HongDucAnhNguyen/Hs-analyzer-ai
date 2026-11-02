import asyncio
import json
import os
from typing import Dict, List

from engine.init_qdrant_db import (chunk_documents_async,
                                   upsert_chunks_to_qdrant_async)

QDRANT_HOST=os.getenv("QDRANT_HOST","34.143.173.34")
QDRANT_PORT=int(os.getenv("QDRANT_PORT",6333))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "hs_code_db")


async def build_semantic_db(documents: List[Dict]) -> None:
    # 1. Chunk documents asynchronously
    chunks = await chunk_documents_async(documents)
    # 2. Upsert chunks to Qdrant asynchronously
    if chunks:
        await upsert_chunks_to_qdrant_async(
            chunks=chunks,
            collection_name=QDRANT_COLLECTION,
            host=QDRANT_HOST,
            port=QDRANT_PORT,
            vector_dim=1536,
        )


async def main():
    
    #TODO: modify the code to load my own documents
    file_path = "/home/sotatek/Downloads/structured_subheadings_v2_all.json"
    with open(file_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
    documents = raw_data.get("subheadings", [])
    await build_semantic_db(documents)


if __name__ == "__main__":
    asyncio.run(main())