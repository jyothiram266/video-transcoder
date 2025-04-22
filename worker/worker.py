# worker/worker.py
import os
import json
import time
import subprocess
import requests
import logging
from typing import Dict, Any
import pika
from minio import Minio
from minio.error import S3Error

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environment variables
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_PORT = int(os.environ.get("RABBITMQ_PORT", 5672))
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
MINIO_HOST = os.environ.get("MINIO_HOST", "minio")
MINIO_PORT = int(os.environ.get("MINIO_PORT", 9000))
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
STORAGE_TYPE = os.environ.get("STORAGE_TYPE", "local")
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")

# Define storage paths
UPLOAD_DIR = "/app/storage/uploads"
OUTPUT_DIR = "/app/storage/output"

# Ensure directories exist
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize MinIO client if needed
minio_client = None
if STORAGE_TYPE == "minio":
    minio_client = Minio(
        f"{MINIO_HOST}:{MINIO_PORT}",
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )

# Resolution mapping to actual dimensions
RESOLUTION_MAP = {
    "360p": "640x360",
    "480p": "854x480",
    "720p": "1280x720",
    "1080p": "1920x1080",
    "2160p": "3840x2160"
}

def update_job_status(job_id: str, status: str) -> None:
    """
    Update the job status by calling the backend API
    """
    try:
        response = requests.post(
            f"{BACKEND_URL}/job/{job_id}/update",
            data={"status": status}
        )
        if response.status_code != 200:
            logger.error(f"Failed to update job status. Response: {response.text}")
    except Exception as e:
        logger.error(f"Error updating job status: {str(e)}")

def transcode_video(job: Dict[str, Any]) -> bool:
    """
    Transcode the video using FFmpeg
    """
    job_id = job["job_id"]
    input_path = job["input_path"]
    output_format = job["format"]
    resolution = RESOLUTION_MAP.get(job["resolution"], "1280x720")
    
    # Define output path
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}.{output_format}")
    
    try:
        # Basic FFmpeg command, can be extended with more options
        command = [
            'ffmpeg',
            '-i', input_path,
            '-s', resolution
        ]
        
        # Add format-specific options
        if output_format == 'gif':
            command.extend([
                '-vf', 'fps=10',  # Lower frame rate for GIFs
                '-loop', '0'      # Loop infinitely
            ])
        else:
            # For video formats, use good quality settings
            command.extend([
                '-c:v', 'libx264' if output_format != 'webm' else 'libvpx-vp9',
                '-crf', '23',     # Quality level (lower is better)
                '-preset', 'medium'  # Encoding speed/compression ratio
            ])
            
            # Add audio settings for video formats
            if output_format != 'gif':
                command.extend([
                    '-c:a', 'aac' if output_format != 'webm' else 'libopus',
                    '-b:a', '128k'  # Audio bitrate
                ])
        
        # Add output path
        command.append(output_path)
        
        # Run the FFmpeg command
        logger.info(f"Starting transcoding job {job_id} to {output_format} at {resolution}")
        subprocess.run(command, check=True)
        
        # If using MinIO, upload the transcoded file
        if STORAGE_TYPE == "minio" and minio_client:
            minio_client.fput_object(
                "transcoded",
                f"{job_id}.{output_format}",
                output_path
            )
            
        logger.info(f"Transcoding job {job_id} completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg process failed for job {job_id}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error in transcoding job {job_id}: {str(e)}")
        return False

def process_message(ch, method, properties, body):
    """
    Process a message from the RabbitMQ queue
    """
    try:
        job = json.loads(body)
        job_id = job["job_id"]
        
        logger.info(f"Received job {job_id}")
        
        # Update job status to "processing"
        update_job_status(job_id, "processing")
        
        # If using MinIO and file not available locally, download it
        if STORAGE_TYPE == "minio" and minio_client:
            input_file = os.path.basename(job["input_path"])
            if not os.path.exists(job["input_path"]):
                try:
                    minio_client.fget_object(
                        "uploads",
                        input_file,
                        job["input_path"]
                    )
                except S3Error as err:
                    logger.error(f"MinIO error: {str(err)}")
                    update_job_status(job_id, "failed")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    return
        
        # Process the video
        success = transcode_video(job)
        
        # Update job status
        if success:
            update_job_status(job_id, "completed")
        else:
            update_job_status(job_id, "failed")
        
        # Acknowledge the message
        ch.basic_ack(delivery_tag=method.delivery_tag)
    
    except json.JSONDecodeError:
        logger.error("Received invalid JSON message")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

def main():
    """
    Main function to setup and start the worker
    """
    # Wait for RabbitMQ to be ready
    max_retries = 30
    retry_count = 0
    while retry_count < max_retries:
        try:
            # Setup RabbitMQ connection
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            # Declare the queue
            channel.queue_declare(queue='video_processing', durable=True)
            
            # Set QoS to limit the number of unacknowledged messages
            channel.basic_qos(prefetch_count=1)
            
            # Register the callback function
            channel.basic_consume(
                queue='video_processing',
                on_message_callback=process_message
            )
            
            logger.info("Worker started and waiting for messages. To exit press CTRL+C")
            
            # Start consuming messages
            channel.start_consuming()
            
            break
        except pika.exceptions.AMQPConnectionError:
            logger.warning(f"Waiting for RabbitMQ to be ready... (attempt {retry_count + 1}/{max_retries})")
            retry_count += 1
            time.sleep(5)
        except Exception as e:
            logger.error(f"Error setting up RabbitMQ connection: {str(e)}")
            retry_count += 1
            time.sleep(5)
    
    if retry_count >= max_retries:
        logger.error("Failed to connect to RabbitMQ after multiple attempts. Exiting.")
        exit(1)

if __name__ == "__main__":
    main()