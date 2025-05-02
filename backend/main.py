# backend/main.py
import os
import json
import uuid
from typing import List
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import pika
from minio import Minio
from minio.error import S3Error
import tempfile
from sqlalchemy.orm import Session

# Import database and models
from database import engine, get_db, Base
import models  # Import all models before creating tables

# Create database tables on startup
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(title="Video Transcoding API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Environment variables
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
MINIO_HOST = os.environ.get("MINIO_HOST", "minio")
MINIO_PORT = int(os.environ.get("MINIO_PORT", 9000))
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")

# Define temporary directory for handling downloads
TEMP_DIR = "/tmp/video-api"
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize MinIO client
minio_client = Minio(
    f"{MINIO_HOST}:{MINIO_PORT}",
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)

# Create buckets if they don't exist
def setup_minio():
    try:
        for bucket in ["uploads", "transcoded"]:
            if not minio_client.bucket_exists(bucket):
                minio_client.make_bucket(bucket)
    except S3Error as err:
        print(f"Error creating MinIO bucket: {err}")

# Connect to RabbitMQ
def get_rabbitmq_connection():
    credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
    parameters = pika.ConnectionParameters(
        host=RABBITMQ_HOST,
        port=RABBITMQ_PORT,
        credentials=credentials
    )
    return pika.BlockingConnection(parameters)

# Create a queue for video processing tasks
def setup_rabbitmq():
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        channel.queue_declare(queue='video_processing', durable=True)
        connection.close()
    except Exception as e:
        print(f"Failed to setup RabbitMQ: {e}")

# Clean up temporary files
def cleanup_temp_file(file_path: str):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Error cleaning up file {file_path}: {e}")

# Call setup once at startup
@app.on_event("startup")
async def startup_event():
    setup_minio()
    setup_rabbitmq()

@app.post("/upload")
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    format: str = Form(...),
    resolution: str = Form(...),
    db: Session = Depends(get_db)
):
    # Validate file
    if not file.filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv')):
        raise HTTPException(status_code=400, detail="Unsupported file format")

    # Validate format
    valid_formats = ["mp4", "webm", "mkv", "avi", "mov", "gif"]
    if format.lower() not in valid_formats:
        raise HTTPException(status_code=400, detail=f"Unsupported output format. Supported formats: {', '.join(valid_formats)}")

    # Validate resolution
    valid_resolutions = ["360p", "480p", "720p", "1080p", "2160p"]
    if resolution not in valid_resolutions:
        raise HTTPException(status_code=400, detail=f"Unsupported resolution. Supported resolutions: {', '.join(valid_resolutions)}")

    try:
        # Generate unique job ID and save the file
        job_id = str(uuid.uuid4())
        original_filename = file.filename
        filename_parts = os.path.splitext(original_filename)
        file_extension = filename_parts[1]
        object_name = f"{job_id}{file_extension}"
        
        # Create a temporary file to store the upload
        temp_file_path = os.path.join(TEMP_DIR, object_name)
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
            
        # Get file size
        file_size = os.path.getsize(temp_file_path)
            
        # Upload to MinIO
        minio_client.fput_object(
            "uploads", 
            object_name, 
            temp_file_path
        )
        
        # Create job metadata and save to database
        new_job = models.Job(
            job_id=job_id,
            filename=original_filename,
            format=format,
            resolution=resolution,
            object_name=object_name,
            status="queued",
            file_size=file_size
        )
        
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        
        # Schedule cleanup of the temporary file
        background_tasks.add_task(cleanup_temp_file, temp_file_path)
        
        # Queue the job in RabbitMQ
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        channel.basic_publish(
            exchange='',
            routing_key='video_processing',
            body=json.dumps(new_job.to_dict()),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        connection.close()
        
        return {"job_id": job_id, "message": "Video uploaded and queued for processing"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process upload: {str(e)}")

@app.get("/jobs")
async def get_jobs(db: Session = Depends(get_db)):
    jobs = db.query(models.Job).all()
    return [job.to_dict() for job in jobs]

@app.get("/job/{job_id}")
async def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()

@app.get("/download/{job_id}")
async def download_video(job_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Video processing not completed yet")
    
    output_filename = f"{job_id}.{job.format}"
    
    # Create a temporary file to serve the download
    temp_output_path = os.path.join(TEMP_DIR, output_filename)
    
    try:
        # Download the file from MinIO
        minio_client.fget_object(
            "transcoded", 
            output_filename, 
            temp_output_path
        )
    except S3Error as err:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve file from storage: {str(err)}")
    
    # Set a filename that's readable to the user
    display_filename = f"{os.path.splitext(job.filename)[0]}_{job.resolution}.{job.format}"
    
    # Schedule cleanup of the temporary file
    background_tasks.add_task(cleanup_temp_file, temp_output_path)
    
    return FileResponse(
        path=temp_output_path,
        filename=display_filename,
        media_type=f"video/{job.format}" if job.format != 'gif' else "image/gif"
    )

# Endpoint to update job status (called by the worker)
@app.post("/job/{job_id}/update")
async def update_job(
    job_id: str, 
    status: str = Form(...), 
    progress: int = Form(None), 
    duration: int = Form(None), 
    error_message: str = Form(None),
    db: Session = Depends(get_db)
):
    job = db.query(models.Job).get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Update job fields
    job.status = status
    
    if progress is not None:
        job.progress = progress
        
    if duration is not None:
        job.duration = duration
        
    if error_message is not None:
        job.error_message = error_message
    
    # Save changes to database
    db.commit()
    db.refresh(job)
    
    return {"job_id": job_id, "status": status}