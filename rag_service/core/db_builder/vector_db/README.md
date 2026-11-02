# Vector Database Builder

This directory contains tools for building and managing vector databases for HS Code search.

## 📁 Directory Structure

```
vector_db/
├── engine/              # Core embedding and chunking logic
│   ├── embedder/       # OpenAI and Gemini embedders
│   ├── chunker/        # Semantic chunking algorithms
│   └── init_qdrant_db.py
├── ingestion/          # 📦 Data ingestion scripts (START HERE!)
│   ├── README_INGESTION.md
│   ├── ingest_asean_openai.py
│   ├── ingest_asean_gemini.py
│   ├── ingest_compendium_openai.py
│   └── ingest_compendium_gemini.py
└── main.py             # Legacy main script
```

## 🚀 Quick Start

**To create vector collections, go to the `ingestion/` folder:**

```bash
cd ingestion/
cat README_INGESTION.md  # Read the documentation
```

### Create Collections

**OpenAI Embeddings:**
```bash
cd ingestion/
python ingest_asean_openai.py
python ingest_compendium_openai.py
```

**Gemini Embeddings:**
```bash
cd ingestion/
python ingest_asean_gemini.py
python ingest_compendium_gemini.py
```

## 📊 Collections

Each script creates a specific collection in Qdrant:

| Script | Collection Name | Data Source | Embedding Model |
|--------|----------------|-------------|-----------------|
| `ingest_asean_openai.py` | `asean_openai` | Vietnamese + English | text-embedding-3-large |
| `ingest_asean_gemini.py` | `asean_gemini` | Vietnamese + English | gemini-embedding-001 |
| `ingest_compendium_openai.py` | `compendium_openai` | French + English | text-embedding-3-large |
| `ingest_compendium_gemini.py` | `compendium_gemini` | French + English | gemini-embedding-001|

## 🔧 How It Works

1. **Load Data** - Reads JSON files from `rag_service/data/`
2. **Chunk Documents** - Uses semantic clustering with embeddings
3. **Generate Embeddings** - Creates 1536-dim vectors
4. **Upload to Qdrant** - Stores in vector database

## ⚙️ Configuration

Set in `.env` file:
- `OPENAI_API_KEY` - For OpenAI embeddings
- `GEMINI_API_KEY` - For Gemini embeddings
- `QDRANT_HOST` - Qdrant server host
- `QDRANT_PORT` - Qdrant server port

## 🔄 Auto-Detection

The API automatically selects the correct collection based on which API key is active:
- Active `OPENAI_API_KEY` → uses `*_openai` collections
- Active `GEMINI_API_KEY` → uses `*_gemini` collections

No code changes needed to switch between providers!

## 📚 More Information

See `ingestion/README_INGESTION.md` for:
- Detailed usage instructions
- Time estimates
- Troubleshooting guide
- Comparison with old methods
