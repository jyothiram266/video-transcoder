# backend/models.py
from sqlalchemy import Column, String, DateTime, Integer, Text, func
from database import Base  # Import Base from database.py instead of redefining it

class Job(Base):
    """Database model for video transcoding jobs"""
    __tablename__ = "jobs"

    job_id = Column(String(36), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    format = Column(String(50), nullable=False)
    resolution = Column(String(50), nullable=False)
    object_name = Column(String(255), nullable=False)
    status = Column(String(50), default="queued")
    progress = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    error_message = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    duration = Column(Integer, nullable=True)  # in seconds

    def to_dict(self):
        """Convert model to dictionary for API responses"""
        return {
            "job_id": self.job_id,
            "filename": self.filename,
            "format": self.format,
            "resolution": self.resolution,
            "object_name": self.object_name,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "error_message": self.error_message,
            "file_size": self.file_size,
            "duration": self.duration
        }