import asyncio
import logging
from typing import Dict, List

from engine.chunker.cluster_semantic_chunker import ClusterSemanticChunker
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("knowledge_base")


async def upsert_chunks_to_qdrant_async(
    chunks: List[Dict],
    collection_name: str,
    host: str,
    port: int,
    vector_dim: int,
) -> None:
    if not chunks:
        log.warning("No chunks to upsert to Qdrant.")
        return

    client = AsyncQdrantClient(host=host, port=port, timeout=60.0)  # 60 second timeout

    try:
        collections_response = await client.get_collections()
        existing_collections = [c.name for c in collections_response.collections]

        if collection_name in existing_collections:
            log.info(f"Deleting existing collection '{collection_name}' to replace with new data...")
            await client.delete_collection(collection_name=collection_name)
            log.info(f"✅ Deleted existing collection: {collection_name}")
        
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )
        log.info(f"✅ Created new Qdrant collection: {collection_name}")

    except Exception as e:
        log.error(f"Failed to create collection '{collection_name}': {e}", exc_info=True)
        return

    vector_dim: int = 1536
    batch_size: int = 100  # Reduced from 512 to avoid timeouts
    points = []
    count_total = 0
    for item in chunks:
        if "id" not in item or "embedding_vector" not in item:
            log.warning(f"Skipping chunk: missing 'id' or 'embedding_vector' (id={item.get('id')})")
            continue

        vec = item["embedding_vector"]
        payload = {k: v for k, v in item.items() if k not in ("id", "embedding_vector")}
        #payload.setdefault("_node_content", payload.get("_node_content") or payload.get("text") or "")
        points.append(PointStruct(
            id=item["id"],
            vector=vec,
            payload=payload
        ))
        if len(points) >= batch_size:
            try:
                log.info(f"Uploading batch of {len(points)} points...")
                await client.upsert(
                    collection_name=collection_name,
                    points=points,  
                    wait=True
                )
                count_total += len(points)
                log.info(f"✅ Upserted batch: {len(points)} points (total={count_total})")
                points = []
            except Exception as e:
                log.error(f"❌ Failed to upsert batch: {e}", exc_info=True)
                # Don't continue if upload fails
                raise
    if points:
        try:
            log.info(f"Uploading final batch of {len(points)} points...")
            await client.upsert(
                collection_name=collection_name,
                points=points,
                wait=True
            )
            count_total += len(points)
            log.info(f"✅ Upserted final batch: {len(points)} points (total={count_total})")
        except Exception as e:
            log.error(f"❌ Failed to upsert final batch: {e}", exc_info=True)
            raise



async def chunk_documents_async(documents: List[Dict], max_chunk_size: int = 512, min_chunk_size: int = 256) -> List[Dict]:
    """Asynchronously chunks a list of documents using semantic clustering."""
    if not documents:
        return []
        
    log.info(f"Starting to chunk {len(documents)} documents asynchronously...")
    chunker = ClusterSemanticChunker(
        max_chunk_size=max_chunk_size,
        min_chunk_size=min_chunk_size
    )
    
    tasks = [chunker.achunk(doc) for doc in documents]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    all_chunks = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            doc_id = documents[i].get('code', f'index {i}')
            log.error(f"Failed to chunk document {doc_id}: {result}", exc_info=True)
        elif result:
            all_chunks.extend(result)
            
    log.info(f"Finished chunking. Generated {len(all_chunks)} chunks in total.")
    return all_chunks
