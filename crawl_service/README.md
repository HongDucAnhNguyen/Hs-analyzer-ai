# Crawl Service

The Crawl Service is designed to search and retrieve HS code rulings from multiple international customs and trade websites. It supports both simple query search and intelligent product-based search with LLM-powered query rewriting.

## Features

- **Multi-source crawling**: Queries 4 different HS code ruling websites in parallel
- **LLM-powered query rewriting**: Converts detailed product information into 3 optimized search queries
- **Unified API**: Single endpoint to search across all sources
- **Structured results**: Returns consistent, structured data from all sources
- **Error handling**: Gracefully handles failures from individual sources
- **Deduplication**: Removes duplicate results across multiple queries

## Supported Sources

1. **CBSA Canada** - Canadian International Trade Tribunal decisions
   - Website: https://www.cbsa-asfc.gc.ca/recourse-recours/decisions-eng.html
   - Searches static HTML tables and retrieves full ruling content

2. **CARM Canada** - Canadian national rulings database
   - Website: https://ccp-pcc.cbsa-asfc.cloud-nuage.canada.ca/en/national-rulings
   - Uses API endpoints to search and retrieve ruling details

3. **US CBP** - US Customs and Border Protection rulings
   - Website: https://rulings.cbp.gov/home
   - Uses search API to find relevant rulings

4. **UK HMRC** - UK advance tariff rulings
   - Website: https://www.tax.service.gov.uk/search-for-advance-tariff-rulings
   - Searches HTML pages and extracts ruling information

## API Endpoints

### POST /api/v1/crawl/search

Search for HS code rulings using a simple query string.

**Request Body:**
```json
{
  "query": "nintendo",
  "max_results_per_source": 10
}
```

**Response:**
```json
{
  "query": "nintendo",
  "rewritten_queries": ["nintendo"],
  "total_results": 4,
  "sources_queried": ["CBSA Canada", "CARM Canada", "US CBP", "UK HMRC"],
  "errors": {},
  "results": [...]
}
```

### POST /api/v1/crawl/hs-ruling

Search for HS code rulings using detailed product information with LLM-powered query rewriting.

**Request Body:**
```json
{
  "product_name": "Máy chiếu phim gia đình (Home Cinema Projector)",
  "science_name": "DIGITAL LIGHT PROCESSING (DLP) PROJECTOR, PORTABLE, WITH BUILT-IN SPEAKER AND WI-FI CONNECTIVITY",
  "product_description": "Máy chiếu sử dụng công nghệ DLP...",
  "function": "Chiếu hình ảnh và video...",
  "structure": "Cấu trúc hỗn hợp...",
  "material": "",
  "specifications": "Độ phân giải: 1920x1080...",
  "max_results_per_source": 10
}
```

**Response:**
```json
{
  "query": "Máy chiếu phim gia đình (Home Cinema Projector)",
  "rewritten_queries": [
    "home cinema DLP video projector with speaker",
    "digital DLP projector with WiFi connectivity", 
    "portable smart multimedia projection apparatus"
  ],
  "total_results": 8,
  "sources_queried": ["CBSA Canada", "CARM Canada", "US CBP", "UK HMRC"],
  "errors": {},
  "results": [
    {
      "source": "CARM Canada",
      "ruling_id": "8000010337",
      "title": "Nintendo Switch 2 Game Card",
      "content": "Product: Nintendo Switch 2 Game Card...",
      "url": "https://...",
      "metadata": {...}
    }
  ]
}
```

**How it works:**
1. Takes detailed product information (compatible with RAG and Classifier service formats)
2. Uses LLM to generate **3 short, practical search queries (2-4 words each)**
3. Queries use **official trade terminology** commonly found in customs rulings
4. Searches all sources with each query in parallel
5. Aggregates and deduplicates results
6. Returns all results with the rewritten queries used

**Example Query Rewriting:**
```
Input: "Máy chiếu phim gia đình (Home Cinema Projector)"
Output queries:
  - "projector apparatus" (2 words)
  - "DLP projector" (2 words)
  - "video projection equipment" (3 words)
```

### GET /api/v1/crawl/health

Health check endpoint for the crawl service.

## Usage Example

```python
import httpx

async def search_rulings():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8080/api/v1/crawl/search",
            json={
                "query": "adapter",
                "max_results_per_source": 5
            }
        )
        data = response.json()
        print(f"Found {data['total_results']} results")
        for result in data['results']:
            print(f"{result['source']}: {result['title']}")
```

## Testing

Run the test script:
```bash
uv run python test_crawl.py
```

## Architecture

```
crawl_service/
├── api/
│   └── v1/
│       └── endpoints.py          # FastAPI endpoints
├── core/
│   ├── models.py                 # Pydantic models
│   └── orchestrator.py           # Orchestrates all crawlers
└── crawlers/
    ├── base.py                   # Base crawler interface
    ├── cbsa_canada.py            # CBSA Canada crawler
    ├── carm_canada.py            # CARM Canada crawler
    ├── us_cbp.py                 # US CBP crawler
    └── uk_hmrc.py                # UK HMRC crawler
```

## Dependencies

- `httpx` - Async HTTP client
- `beautifulsoup4` - HTML parsing
- `pydantic` - Data validation
- `fastapi` - API framework
