"""
Unified API Gateway for HS Code Services
Combines RAG Service and Classifier Service into a single API
"""

import logging
import sys
from typing import Annotated

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Import centralized logging configuration
from logging_config import setup_logging

# Import authentication
from auth import auth_router, get_current_active_user, require_engagement_code
from auth.models import User

# Setup centralized logging
setup_logging()

logger = logging.getLogger(__name__)
logger.info("Starting Unified HS Code API Gateway")

# ============================================================================
# Initialize FastAPI Application
# ============================================================================
app = FastAPI(
    title="HS Code Services API Gateway",
    description="Unified API for HS Code Search (RAG) and Classification Services",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ============================================================================
# CORS Configuration
# ============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Exception Handlers
# ============================================================================
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    logger.error(f"Validation error: {errors}")
    
    # Convert error objects to JSON-serializable format
    serializable_errors = []
    for error in errors:
        serializable_error = error.copy()
        if 'ctx' in serializable_error and 'error' in serializable_error['ctx']:
            serializable_error['ctx']['error'] = str(serializable_error['ctx']['error'])
        serializable_errors.append(serializable_error)
    
    return JSONResponse(
        status_code=422,
        content={"detail": serializable_errors}
    )

# ============================================================================
# Import and Setup Services
# ============================================================================
# ============================================================================
# Authentication Router (no auth required for login)
# ============================================================================
try:
    logger.info("Importing Authentication Service...")
    app.include_router(auth_router, prefix="/api/v1")
    logger.info("✓ Auth routes registered at /api/v1/auth/*")
except Exception as e:
    logger.error(f"Failed to import Auth Service: {e}")
    logger.error("Authentication will not be available")

# ============================================================================
# Protected Service Routes (require authentication)
# ============================================================================

try:
    # Import RAG Service components
    logger.info("Importing RAG Service...")
    from rag_service.api.http.v1.controller import router as rag_router
    from rag_service.core.logfire_config import setup_logfire
    
    # Setup Logfire monitoring
    setup_logfire()
    
    # Include RAG Service routes - controller already has /search prefix
    # Final path: /api/v1/search/hscode
    app.include_router(
        rag_router,
        prefix="/api/v1",
        dependencies=[Depends(get_current_active_user), Depends(require_engagement_code)]
    )
    logger.info("✓ RAG Service routes registered at /api/v1/search/* (protected)")
    
except Exception as e:
    logger.error(f"Failed to import RAG Service: {e}")
    logger.error("RAG Service endpoints will not be available")

try:
    # Import Classifier Service components
    logger.info("Importing Classifier Service...")
    from classifier_service.core.config import setup_environment
    from classifier_service.api.v1 import endpoints as classifier_endpoints
    
    # Setup classifier environment
    setup_environment()
    
    # Include Classifier Service routes - no prefix in endpoints.py
    # Final paths: /api/v1/classify/, /api/v1/classify/async
    app.include_router(
        classifier_endpoints.router, 
        prefix="/api/v1",
        dependencies=[Depends(get_current_active_user), Depends(require_engagement_code)]
    )
    logger.info("✓ Classifier Service routes registered at /api/v1/classify/* (protected)")
    
except Exception as e:
    logger.error(f"Failed to import Classifier Service: {e}")
    logger.error("Classifier Service endpoints will not be available")

try:
    # Import Crawl Service components
    logger.info("Importing Crawl Service...")
    from crawl_service.api.v1 import endpoints as crawl_endpoints
    
    # Include Crawl Service routes
    # Final paths: /api/v1/crawl/*
    app.include_router(
        crawl_endpoints.router,
        prefix="/api/v1",
        dependencies=[Depends(get_current_active_user), Depends(require_engagement_code)]
    )
    logger.info("✓ Crawl Service routes registered at /api/v1/crawl/* (protected)")
    
except Exception as e:
    logger.error(f"Failed to import Crawl Service: {e}")
    logger.error("Crawl Service endpoints will not be available")

try:
    # Import HS Analyzer Service components
    logger.info("Importing HS Analyzer Service...")
    from hs_analyzer_service.api.v1 import endpoints as analyzer_endpoints
    
    # Include HS Analyzer Service routes
    # Final paths: /api/v1/analyze/*
    app.include_router(
        analyzer_endpoints.router,
        prefix="/api/v1",
        dependencies=[Depends(get_current_active_user), Depends(require_engagement_code)]
    )
    logger.info("✓ HS Analyzer Service routes registered at /api/v1/analyze/* (protected)")
    
except Exception as e:
    logger.error(f"Failed to import HS Analyzer Service: {e}")
    logger.error("HS Analyzer Service endpoints will not be available")

try:
    # Import Report Service components
    logger.info("Importing Report Service...")
    from report_service.api.v1 import endpoints as report_endpoints
    
    # Include Report Service routes
    # Final paths: /api/v1/report/*
    app.include_router(
        report_endpoints.router,
        prefix="/api/v1",
        dependencies=[Depends(get_current_active_user), Depends(require_engagement_code)]
    )
    logger.info("✓ Report Service routes registered at /api/v1/report/* (protected)")
    
except Exception as e:
    logger.error(f"Failed to import Report Service: {e}")
    logger.error("Report Service endpoints will not be available")

# ============================================================================
# Root and Health Endpoints
# ============================================================================
@app.get("/", tags=["General"])
async def root():
    """Welcome endpoint with service information"""
    return {
        "message": "HS Code Services API Gateway",
        "version": "2.4.0",
        "authentication": {
            "login": "/api/v1/auth/login (POST)",
            "refresh": "/api/v1/auth/refresh (POST)",
            "logout": "/api/v1/auth/logout (POST)"
        },
        "services": {
            "search": "/api/v1/search/* (protected)",
            "classification": "/api/v1/classify/* (protected)",
            "crawl": "/api/v1/crawl/* (protected)",
            "hs_analyzer": "/api/v1/analyze/* (protected)",
            "report": "/api/v1/report/* (protected)"
        },
        "documentation": "/docs"
    }

@app.get("/health", tags=["General"])
async def health_check():
    """Health check endpoint for all services"""
    return {
        "status": "healthy",
        "services": {
            "api_gateway": "running",
            "auth_service": "available",
            "rag_service": "available",
            "classifier_service": "available",
            "crawl_service": "available",
            "analyzer_service": "available",
            "report_service": "available"
        }
    }

@app.get("/services", tags=["General"])
async def list_services():
    """List all available services and their endpoints"""
    return {
        "services": [
            {
                "name": "Search Service",
                "description": "HS Code search using RAG (Retrieval-Augmented Generation)",
                "base_path": "/api/v1/search",
                "endpoints": {
                    "asean_search": "/api/v1/search/asean",
                    "compendium_search": "/api/v1/search/compendium"
                },
                "cache": {
                    "stats": "/api/v1/search/cache/stats",
                    "clear": "/api/v1/search/cache/clear"
                }
            },
            {
                "name": "Classification Service",
                "description": "Product classification into HS Code hierarchy",
                "base_path": "/api/v1/classify",
                "endpoints": {
                    "classify_sync": "/api/v1/classify/",
                    "classify_async": "/api/v1/classify/async",
                    "task_status": "/api/v1/classify/async/{task_id}"
                },
                "cache": {
                    "stats": "/api/v1/classify/cache/stats",
                    "clear": "/api/v1/classify/cache/clear"
                }
            },
            {
                "name": "Crawl Service",
                "description": "Crawl HS code rulings from multiple sources with query rewriting",
                "base_path": "/api/v1/crawl",
                "endpoints": {
                    "hs_ruling": "/api/v1/crawl/hs-ruling",
                    "hs_ruling_async": "/api/v1/crawl/hs-ruling/async",
                    "hs_ruling_task_status": "/api/v1/crawl/hs-ruling/async/{task_id}",
                    "hs_database": "/api/v1/crawl/hs_database",
                    "hs_database_async": "/api/v1/crawl/hs_database/async",
                    "hs_database_task_status": "/api/v1/crawl/hs_database/async/{task_id}",
                    "health": "/api/v1/crawl/health"
                },
                "cache": {
                    "stats": "/api/v1/crawl/cache/stats",
                    "clear": "/api/v1/crawl/cache/clear"
                }
            },
            {
                "name": "HS Analyzer Service",
                "description": "Phân tích và đánh giá mức độ phù hợp của các mã HS với sản phẩm sử dụng LLM",
                "base_path": "/api/v1/analyze",
                "endpoints": {
                    "analyze_hs_codes": "/api/v1/analyze/hs-codes"
                }
            },
            {
                "name": "Report Service",
                "description": "Analyze TKR Excel reports and generate HS Consistency, Value Variance, and NTM reports with Train Links. Upload Excel → Get Excel with report sheets.",
                "base_path": "/api/v1/report",
                "endpoints": {
                    "analyze": "/api/v1/report/analyze",
                    "upload_url": "/api/v1/report/upload-url",
                    "process": "/api/v1/report/process",
                    "process_async": "/api/v1/report/process/async",
                    "task_status": "/api/v1/report/task/{task_id}",
                    "etariff_process_async": "/api/v1/report/e-tariff/process/async",
                    "etariff_task_status": "/api/v1/report/e-tariff/task/{task_id}"
                }
            }
        ]
    }

# ============================================================================
# Debug Endpoints (for development)
# ============================================================================
@app.get("/debug/routes", tags=["Debug"])
async def debug_routes():
    """List all registered routes"""
    routes = []
    for route in app.routes:
        routes.append({
            "path": route.path,
            "name": route.name,
            "methods": list(route.methods) if hasattr(route, "methods") else None,
        })
    return {"routes": routes}

# ============================================================================
# Run Server
# ============================================================================
if __name__ == "__main__":
    import uvicorn
    import os
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8080"))
    workers = int(os.getenv("API_WORKERS", "4"))
    
    logger.info(f"Starting unified API server on {host}:{port}")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv("DEBUG", "False").lower() == "true"
    )
