"""
API v1 Schemas for Crawl Service - Task Management
"""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class TaskSubmitResponse(BaseModel):
    """Response when submitting an async crawl task"""
    task_id: str = Field(..., description="Unique ID for the crawl task")
    status: str = Field(..., description="Current status of the task")
    message: str = Field(..., description="Information message")


class TaskStatusResponse(BaseModel):
    """Response for checking task status"""
    task_id: str = Field(..., description="Task ID")
    status: str = Field(..., description="Task status: PENDING, STARTED, PROGRESS, SUCCESS, FAILURE")
    result: Optional[Dict[str, Any]] = Field(None, description="Crawl result if task is complete")
    progress: Optional[Dict[str, Any]] = Field(None, description="Progress information if task is in progress")
    partial_results: Optional[Dict[str, Any]] = Field(None, description="Partial results available during processing")
    error: Optional[str] = Field(None, description="Error message if task failed")

