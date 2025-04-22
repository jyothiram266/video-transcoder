# backend/models.py
from enum import Enum
from pydantic import BaseModel

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Job(BaseModel):
    id: str
    filename: str
    format: str
    resolution: str
    status: JobStatus
    input_path: str
    output_path: str