"""
Ingest HS Code data into Qdrant using Gemini embeddings
Creates a new collection with Gemini embeddings (gemini-embedding-001, dim=1536)
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
VECTOR_DB_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(VECTOR_DB_ROOT))

from dotenv import load_dotenv
from engine.init_qdrant_db import chunk_documents_async, upsert_chunks_to_qdrant_async

# Load environment variables
load_dotenv()

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "34.143.173.34")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION_GEMINI", "hs_code_db_gemini")  # New collection name
DATA_DIR = "rag_service/data"
VECTOR_DIM = 1536  # Gemini embedding-001 with 1536 dimensions


async def load_json_files(data_dir: str) -> List[Dict]:
    """Load all JSON files from the data directory."""
    documents = []
    data_path = Path(data_dir)
    
    if not data_path.exists():
        raise ValueError(f"Data directory does not exist: {data_dir}")
    
    json_files = list(data_path.glob("*.json"))
    
    if not json_files:
        raise ValueError(f"No JSON files found in: {data_dir}")
    
    print(f"\n📂 Found {len(json_files)} JSON files:")
    for json_file in json_files:
        print(f"   - {json_file.name} ({json_file.stat().st_size / 1024 / 1024:.2f} MB)")
    
    for json_file in json_files:
        try:
            print(f"\n📖 Loading: {json_file.name}")
            with open(json_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            
            # Try different possible keys for the document list
            if isinstance(raw_data, list):
                docs = raw_data
            elif isinstance(raw_data, dict):
                # Try common keys
                docs = (
                    raw_data.get("subheadings") or
                    raw_data.get("data") or
                    raw_data.get("documents") or
                    raw_data.get("items") or
                    []
                )
            else:
                docs = []
            
            if docs:
                documents.extend(docs)
                print(f"   ✅ Loaded {len(docs)} documents from {json_file.name}")
            else:
                print(f"   ⚠️  No documents found in {json_file.name}")
                
        except json.JSONDecodeError as e:
            print(f"   ❌ Failed to parse {json_file.name}: {e}")
        except Exception as e:
            print(f"   ❌ Error loading {json_file.name}: {e}")
    
    return documents


async def build_semantic_db_with_gemini(documents: List[Dict]) -> None:
    """Build semantic database with Gemini embeddings."""
    if not documents:
        print("❌ No documents to process!")
        return
    
    print(f"\n🔨 Processing {len(documents)} documents...")
    
    # 1. Chunk documents asynchronously
    print("\n📦 Chunking documents...")
    chunks = await chunk_documents_async(documents)
    
    if not chunks:
        print("❌ No chunks generated!")
        return
    
    print(f"✅ Generated {len(chunks)} chunks")
    
    # 2. Upsert chunks to Qdrant asynchronously
    print(f"\n⬆️  Upserting to Qdrant collection: '{QDRANT_COLLECTION}'")
    print(f"   Host: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"   Vector dimension: {VECTOR_DIM}")
    
    await upsert_chunks_to_qdrant_async(
        chunks=chunks,
        collection_name=QDRANT_COLLECTION,
        host=QDRANT_HOST,
        port=QDRANT_PORT,
        vector_dim=VECTOR_DIM,
    )
    
    print(f"\n✅ Successfully created collection: '{QDRANT_COLLECTION}'")


async def main():
    """Main execution function."""
    print("=" * 80)
    print("🚀 HS Code Data Ingestion with Gemini Embeddings")
    print("=" * 80)
    
    # Check if Gemini API key is set
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        print("❌ GEMINI_API_KEY not found in environment variables!")
        print("   Please set it in your .env file.")
        return
    
    print(f"\n✅ Gemini API Key: {gemini_key[:10]}...{gemini_key[-5:]}")
    print(f"📁 Data Directory: {DATA_DIR}")
    print(f"🗄️  Qdrant Host: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"📊 New Collection: {QDRANT_COLLECTION}")
    print(f"📐 Vector Dimension: {VECTOR_DIM}")
    
    try:
        # Load all JSON files
        documents = await load_json_files(DATA_DIR)
        
        if not documents:
            print("\n❌ No documents loaded! Check your JSON files.")
            return
        
        print(f"\n✅ Total documents loaded: {len(documents)}")
        
        # Build semantic database
        await build_semantic_db_with_gemini(documents)
        
        print("\n" + "=" * 80)
        print("✅ INGESTION COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print(f"\n📊 Summary:")
        print(f"   - Documents processed: {len(documents)}")
        print(f"   - Collection name: {QDRANT_COLLECTION}")
        print(f"   - Embedding model: gemini-embedding-001 (1536 dim)")
        print(f"   - Host: {QDRANT_HOST}:{QDRANT_PORT}")
        print(f"\n💡 To use this collection, set in your .env:")
        print(f"   QDRANT_COLLECTION={QDRANT_COLLECTION}")
        
    except Exception as e:
        print(f"\n❌ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
