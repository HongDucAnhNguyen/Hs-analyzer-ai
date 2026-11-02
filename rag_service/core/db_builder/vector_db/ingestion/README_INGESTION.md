# Embedding Ingestion Scripts

Creates vector collections for ASEAN and WCO Compendium data with both OpenAI and Gemini embeddings.

## Prerequisites

1. **Data Files**: Place your JSON data files in `rag_service/data/`
   - ASEAN data: `structured_subheadings_v2_all.json` (~17 MB)
   - Compendium data: `wco_structured_subheadings_all.json` (~11 MB)

2. **Environment Variables**: Set API keys in `.env` at project root
   ```bash
   OPENAI_API_KEY="your-openai-key"
   GEMINI_API_KEY="your-gemini-key"
   QDRANT_HOST="34.143.173.34"
   QDRANT_PORT=6333
   ```

3. **Python Environment**: Use either:
   - Conda: `conda activate temphscode`
   - UV: Run with `uv run` (automatically manages dependencies)

## Quick Start

### Running from Project Root (Recommended)

All commands should be run from the project root directory:

```bash
cd /path/to/unified_api
```

#### Using Conda Environment

```bash
# OpenAI Embeddings
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_asean_openai.py
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_openai.py

# Gemini Embeddings
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_asean_gemini.py
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_gemini.py
```

#### Using UV (Alternative)

```bash
# OpenAI Embeddings
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_asean_openai.py
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_openai.py

# Gemini Embeddings
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_asean_gemini.py
uv run rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_gemini.py
```

## Collections Created

| Script | Collection Name | Embedding Model | Dimensions | Data Source |
|--------|----------------|-----------------|------------|-------------|
| `ingest_asean_openai.py` | `asean_openai` | text-embedding-3-large | 1536 | Vietnamese + English |
| `ingest_compendium_openai.py` | `compendium_openai` | text-embedding-3-large | 1536 | French + English |
| `ingest_asean_gemini.py` | `asean_gemini` | gemini-embedding-001 | 1536 | Vietnamese + English |
| `ingest_compendium_gemini.py` | `compendium_gemini` | gemini-embedding-001 | 1536 | French + English |

## Important Notes

### ⚠️ Collection Replacement
- Scripts will **DELETE and REPLACE** existing collections with the same name
- All previous data in the collection will be lost
- Make sure you have the correct data file before running

### 📂 Data File Locations
- Scripts automatically use relative paths: `rag_service/data/`
- No need to modify paths in the code
- Just ensure your JSON files are in the correct directory

### ⏱️ Time Estimates
- **ASEAN**: ~30-60 minutes (1300+ documents)
- **Compendium**: ~20-40 minutes (728 documents)
- Time varies based on API rate limits and network speed

## Configuration

### OpenAI
- **Embedding Model**: `text-embedding-3-large`
- **Dimensions**: `1536`
- **API Key**: Set in `.env` as `OPENAI_API_KEY`

### Gemini
- **Embedding Model**: `gemini-embedding-001`
- **Dimensions**: `1536`
- **API Key**: Set in `.env` as `GEMINI_API_KEY`

### Qdrant
- **Host**: `34.143.173.34:6333` (or set via `QDRANT_HOST` and `QDRANT_PORT` in `.env`)

## Using the Collections

Collections are **auto-detected** based on which API key is active in `.env`:

- If `OPENAI_API_KEY` is active → uses `asean_openai` and `compendium_openai`
- If only `GEMINI_API_KEY` is active → uses `asean_gemini` and `compendium_gemini`

**No code changes needed!** Just comment/uncomment the API key in `.env` to switch between providers.

## Troubleshooting

### Data File Not Found
```
ValueError: Data file does not exist: ...
```
**Solution**: Ensure JSON files are in `rag_service/data/` directory

### API Key Error
```
❌ OPENAI_API_KEY not found in environment variables!
```
**Solution**: Check `.env` file at project root and ensure the API key is set

### Connection Error
```
Failed to create collection: Connection refused
```
**Solution**: Check Qdrant server is accessible at configured host:port

### Wrong Embedder Used
**Solution**: Gemini scripts temporarily disable OpenAI key during execution to ensure correct embedder

## Example: Replacing Compendium Data with New File

If you have a new Compendium file to ingest:

1. **Copy the file to data directory:**
   ```bash
   cp /path/to/wco_structured_subheadings_all\ \(1\).json rag_service/data/
   ```

2. **Run ingestion from project root:**
   ```bash
   cd /path/to/unified_api
   
   # For OpenAI
   conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_openai.py
   
   # For Gemini
   conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_compendium_gemini.py
   ```

3. **Collections will be automatically replaced** with the new data

## Advanced: Unified Collection (Legacy)

For creating a single unified collection with all data:

```bash
conda run -n temphscode python rag_service/core/db_builder/vector_db/ingestion/ingest_unified_gemini.py
```

Creates: `hs_code_db_gemini` (contains both ASEAN and Compendium data)

**Note**: The separate collection approach (ASEAN + Compendium) is recommended for better organization and faster queries.
