# backend/main.py
import os
import json
import uuid
import shutil
from typing import List
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import pika
from minio import Minio
from minio.error import S3Error

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
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "local")  # 'local' or 'minio'

# Define storage paths
UPLOAD_DIR = "/app/storage/uploads"
OUTPUT_DIR = "/app/storage/output"

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# In-memory job storage (in production, use a database)
jobs = {}

# Initialize MinIO client if needed
minio_client = None
if STORAGE_TYPE == "minio":
    minio_client = Minio(
        f"{MINIO_HOST}:{MINIO_PORT}",
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    
    # Create buckets if they don't exist
    for bucket in ["uploads", "transcoded"]:
        try:
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

# Call setup once at startup
@app.on_event("startup")
async def startup_event():
    setup_rabbitmq()

@app.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    format: str = Form(...),
    resolution: str = Form(...)
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
        
        # Define paths
        upload_path = os.path.join(UPLOAD_DIR, f"{job_id}{file_extension}")
        
        # Save file locally
        with open(upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # If using MinIO, upload to it as well
        if STORAGE_TYPE == "minio" and minio_client:
            minio_client.fput_object(
                "uploads", 
                f"{job_id}{file_extension}", 
                upload_path
            )
        
        # Create job metadata
        job_info = {
            "job_id": job_id,
            "filename": original_filename,
            "format": format,
            "resolution": resolution,
            "input_path": upload_path,
            "status": "queued",
            "storage_type": STORAGE_TYPE
        }
        
        # Save job metadata
        jobs[job_id] = job_info
        
        # Queue the job in RabbitMQ
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        
        channel.basic_publish(
            exchange='',
            routing_key='video_processing',
            body=json.dumps(job_info),
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            )
        )
        connection.close()
        
        return {"job_id": job_id, "message": "Video uploaded and queued for processing"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process upload: {str(e)}")

@app.get("/jobs")
async def get_jobs():
    return list(jobs.values())

@app.get("/job/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]

@app.get("/download/{job_id}")
async def download_video(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = jobs[job_id]
    
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Video processing not completed yet")
    
    output_filename = f"{job_id}.{job['format']}"
    output_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # If using MinIO, download the file first
    if STORAGE_TYPE == "minio" and minio_client:
        try:
            minio_client.fget_object(
                "transcoded", 
                output_filename, 
                output_path
            )
        except S3Error as err:
            raise HTTPException(status_code=500, detail=f"Failed to retrieve file from storage: {str(err)}")
    
    # Check if file exists locally
    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Transcoded file not found")
    
    # Set a filename that's readable to the user
    display_filename = f"{os.path.splitext(job['filename'])[0]}_{job['resolution']}.{job['format']}"
    
    return FileResponse(
        path=output_path,
        filename=display_filename,
        media_type=f"video/{job['format']}" if job['format'] != 'gif' else "image/gif"
    )

# Endpoint to update job status (called by the worker)
@app.post("/job/{job_id}/update")
async def update_job(job_id: str, status: str = Form(...)):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    jobs[job_id]["status"] = status
    return {"job_id": job_id, "status": status}