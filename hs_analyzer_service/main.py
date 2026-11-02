"""
HS Code Analyzer Service - Standalone FastAPI Application
Analyzes and ranks HS codes for product classification using LLM
"""

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from hs_analyzer_service.api.v1 import endpoints as v1_endpoints

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="HS Code Analyzer API",
    description="""
    API to analyze and evaluate the compatibility of HS codes with products.
    
    **Key Features:**
    - Uses LLM to analyze HS codes based on Harmonized System (HS) knowledge
    - Evaluates compatibility with scores from 0.0 to 1.0
    - Provides detailed reasoning in Vietnamese
    - Recommends the most suitable HS code
    """,
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Custom Exception Handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )


# Include API Routers
app.include_router(v1_endpoints.router, prefix="/api/v1")


@app.get("/")
def read_root():
    return {
        "message": "HS Code Analyzer API",
        "description": "Analyze and evaluate HS code compatibility with products",
        "docs": "/docs",
        "version": "1.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    import os
    
    host = os.getenv("ANALYZER_HOST", "0.0.0.0")
    port = int(os.getenv("ANALYZER_PORT", "8083"))
    
    logger.info(f"Starting HS Code Analyzer API on {host}:{port}")
    uvicorn.run(
        "hs_analyzer_service.main:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "False").lower() == "true"
    )
