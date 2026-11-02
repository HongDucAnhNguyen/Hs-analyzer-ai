import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from classifier_service.core.config import setup_environment
from classifier_service.api.v1 import endpoints as v1_endpoints

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 1. Setup Environment
setup_environment()

# 2. Initialize FastAPI app
app = FastAPI(
    title="HS Code Classification API",
    description="API to classify products into HS Code Sections, Chapters, Headings, and Subheadings.",
    version="1.1.0"
)

# 2.1 Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2.2 Custom Exception Handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

# 3. Include API Routers
app.include_router(v1_endpoints.router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to the HS Code Classification API. Use the /docs endpoint to see the API documentation."}
