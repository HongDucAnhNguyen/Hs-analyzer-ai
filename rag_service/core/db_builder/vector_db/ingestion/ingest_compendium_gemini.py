"""
Ingest WCO Compendium HS Code data into Qdrant using Gemini embeddings
Creates a new collection 'compendium_gemini' with gemini-embedding-001 (dim=1536)
Data source: wco_structured_subheadings_all.json
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
QDRANT_COLLECTION = "compendium_gemini"  # New collection name for Compendium with Gemini
DATA_FILE = "rag_service/data/wco_structured_subheadings_all.json"
VECTOR_DIM = 1536  # Gemini embedding-001 with 1536 dimensions


async def load_compendium_data(file_path: str) -> List[Dict]:
    """Load WCO Compendium JSON data file."""
    if not Path(file_path).exists():
        raise ValueError(f"Data file does not exist: {file_path}")
    
    print(f"\n📂 Loading WCO Compendium data file:")
    print(f"   - {Path(file_path).name} ({Path(file_path).stat().st_size / 1024 / 1024:.2f} MB)")
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        
        # Try different possible keys for the document list
        if isinstance(raw_data, list):
            documents = raw_data
        elif isinstance(raw_data, dict):
            # Try common keys
            documents = (
                raw_data.get("subheadings") or
                raw_data.get("data") or
                raw_data.get("documents") or
                raw_data.get("items") or
                []
            )
        else:
            documents = []
        
        if documents:
            print(f"   ✅ Loaded {len(documents)} documents")
        else:
            print(f"   ⚠️  No documents found in file")
            
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON file: {e}")
    except Exception as e:
        raise ValueError(f"Error loading file: {e}")
    
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
    print("🚀 WCO Compendium HS Code Data Ingestion with Gemini Embeddings")
    print("=" * 80)
    
    # Check if Gemini API key is set
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        print("❌ GEMINI_API_KEY not found in environment variables!")
        print("   Please set it in your .env file.")
        return
    
    # Temporarily disable OpenAI key to force Gemini usage
    openai_key_backup = os.getenv("OPENAI_API_KEY")
    if openai_key_backup:
        print("\n⚠️  OpenAI API key detected - temporarily disabling to use Gemini")
        os.environ["OPENAI_API_KEY"] = ""
    
    print(f"\n✅ Gemini API Key: {gemini_key[:10]}...{gemini_key[-5:]}")
    print(f"📁 Data File: {DATA_FILE}")
    print(f"🗄️  Qdrant Host: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"📊 New Collection: {QDRANT_COLLECTION}")
    print(f"📐 Vector Dimension: {VECTOR_DIM}")
    print(f"🤖 Embedding Model: gemini-embedding-001")
    
    try:
        # Load Compendium data
        documents = await load_compendium_data(DATA_FILE)
        
        if not documents:
            print("\n❌ No documents loaded! Check your JSON file.")
            return
        
        print(f"\n✅ Total documents loaded: {len(documents)}")
        
        # Build semantic database
        await build_semantic_db_with_gemini(documents)
        
        print("\n" + "=" * 80)
        print("✅ WCO COMPENDIUM INGESTION COMPLETED SUCCESSFULLY!")
        print("=" * 80)
        print(f"\n📊 Summary:")
        print(f"   - Documents processed: {len(documents)}")
        print(f"   - Collection name: {QDRANT_COLLECTION}")
        print(f"   - Embedding model: gemini-embedding-001 (1536 dim)")
        print(f"   - Data source: WCO Compendium (French + English)")
        print(f"   - Host: {QDRANT_HOST}:{QDRANT_PORT}")
        print(f"\n💡 To use this collection in search endpoint:")
        print(f"   POST /api/v1/search/compendium")
        print(f"   (with GEMINI_API_KEY active, auto-detects to 'compendium_gemini')")
        
    except Exception as e:
        print(f"\n❌ Error during ingestion: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore OpenAI key
        if openai_key_backup:
            os.environ["OPENAI_API_KEY"] = openai_key_backup


if __name__ == "__main__":
    asyncio.run(main())
