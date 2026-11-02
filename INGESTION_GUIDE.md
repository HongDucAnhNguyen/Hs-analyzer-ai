# Quick Ingestion Guide

Quick reference for ingesting data into Qdrant vector database.

## 🚀 Quick Commands

Run these commands from the **project root** (`unified_api/`):

### Using Conda (temphscode environment)

```bash
# Ingest ASEAN data (Vietnamese + English)
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_asean_openai.py      # OpenAI
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_asean_gemini.py      # Gemini

# Ingest Compendium data (French + English)
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_openai.py # OpenAI
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_gemini.py # Gemini
```

### Using UV

```bash
# Ingest ASEAN data
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_asean_openai.py
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_asean_gemini.py

# Ingest Compendium data
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_openai.py
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_gemini.py
```

## 📋 Prerequisites

1. **Data files must be in**: `rag_service/data/`
   - `structured_subheadings_v2_all.json` - ASEAN data (~17 MB)
   - `wco_structured_subheadings_all.json` - Compendium data (~11 MB)

2. **API keys in `.env`**:
   ```
   OPENAI_API_KEY="your-key"
   GEMINI_API_KEY="your-key"
   ```

3. **Qdrant accessible** at `34.143.173.34:6333`

## ⚠️ Important Notes

- **Collections will be REPLACED**: Old data with same collection name will be deleted
- **Run from project root**: Commands assume you're in `unified_api/` directory
- **Time**: ASEAN ~30-60 min, Compendium ~20-40 min

## 📊 Collections Created

| Script | Collection Name | Embedding | Dimensions |
|--------|----------------|-----------|------------|
| `ingest_asean_openai.py` | `asean_openai` | OpenAI text-embedding-3-large | 1536 |
| `ingest_asean_gemini.py` | `asean_gemini` | Gemini embedding-001 | 1536 |
| `ingest_compendium_openai.py` | `compendium_openai` | OpenAI text-embedding-3-large | 1536 |
| `ingest_compendium_gemini.py` | `compendium_gemini` | Gemini embedding-001 | 1536 |

## 📖 Full Documentation

See detailed documentation: `rag_service/core/db_builder/vector_db/ingestion/README_INGESTION.md`
