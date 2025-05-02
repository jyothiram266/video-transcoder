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
BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")

# Define temp storage paths for processing
TEMP_DIR = "/tmp/worker"
os.makedirs(TEMP_DIR, exist_ok=True)

# Initialize MinIO client
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

def update_job_status(job_id: str, status: str, progress: int = None, duration: int = None, error_message: str = None) -> None:
    """
    Update the job status by calling the backend API
    """
    try:
        data = {"status": status}
        if progress is not None:
            data["progress"] = progress
        if duration is not None:
            data["duration"] = duration
        if error_message is not None:
            data["error_message"] = error_message
            
        response = requests.post(
            f"{BACKEND_URL}/job/{job_id}/update",
            data=data
        )
        if response.status_code != 200:
            logger.error(f"Failed to update job status. Response: {response.text}")
    except Exception as e:
        logger.error(f"Error updating job status: {str(e)}")

def get_video_duration(input_path: str) -> int:
    """
    Get video duration in seconds using FFprobe
    """
    try:
        cmd = [
            'ffprobe', 
            '-v', 'error', 
            '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', 
            input_path
        ]
        output = subprocess.check_output(cmd).decode('utf-8').strip()
        return int(float(output))
    except Exception as e:
        logger.error(f"Error getting video duration: {str(e)}")
        return 0

def transcode_video(job: Dict[str, Any]) -> bool:
    """
    Transcode the video using FFmpeg
    """
    job_id = job["job_id"]
    object_name = job["object_name"]
    output_format = job["format"]
    resolution = RESOLUTION_MAP.get(job["resolution"], "1280x720")
    
    # Define paths for processing
    input_path = os.path.join(TEMP_DIR, object_name)
    output_path = os.path.join(TEMP_DIR, f"{job_id}.{output_format}")
    
    try:
        # Clear any potential existing files that could cause conflicts
        # List and log all files in the temp directory to debug
        logger.info(f"Files in {TEMP_DIR} before cleanup:")
        for file in os.listdir(TEMP_DIR):
            logger.info(f"- {file}")
        
        # Check and remove output file specifically
        if os.path.exists(output_path):
            os.remove(output_path)
            logger.info(f"Removed existing output file: {output_path}")
        
        # Download input file from MinIO
        try:
            minio_client.fget_object(
                "uploads",
                object_name,
                input_path
            )
            logger.info(f"Successfully downloaded input file to {input_path}")
        except S3Error as err:
            logger.error(f"MinIO download error: {str(err)}")
            update_job_status(job_id, "failed", error_message=f"Download error: {str(err)}")
            return False
        
        # Get video duration for progress tracking
        duration = get_video_duration(input_path)
        
        # Log files again after download
        logger.info(f"Files in {TEMP_DIR} after download:")
        for file in os.listdir(TEMP_DIR):
            logger.info(f"- {file}")
        
        # Generate a unique output filename with timestamp to avoid conflicts
        unique_output_filename = f"{job_id}_{int(time.time())}.{output_format}"
        output_path = os.path.join(TEMP_DIR, unique_output_filename)
        logger.info(f"Using unique output path: {output_path}")
        
        # Basic FFmpeg command, with both -y flag and specific output filename
        command = [
            'ffmpeg',
            '-y',  # Force overwrite without asking
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
        
        # Add progress tracking
        progress_file = os.path.join(TEMP_DIR, f"{job_id}_progress.txt")
        command.extend([
            '-progress', f'file://{progress_file}',
        ])
        
        # Add output path
        command.append(output_path)
        
        # Log the full command for debugging
        logger.info(f"FFmpeg command: {' '.join(command)}")
        
        # Run the FFmpeg command in the background
        logger.info(f"Starting transcoding job {job_id} to {output_format} at {resolution}")
        
        # Start FFmpeg process with full stderr capture
        process = subprocess.Popen(command, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        
        # Track progress while the process is running
        last_progress = 0
        while True:
            # Check if process has finished
            if process.poll() is not None:
                break
                
            # Try to read progress from FFmpeg progress file
            if os.path.exists(progress_file):
                try:
                    with open(progress_file, 'r') as f:
                        progress_data = f.read()
                        
                    # Parse progress info
                    for line in progress_data.splitlines():
                        if line.startswith("out_time_ms="):
                            current_time_ms = int(line.split("=")[1])
                            if duration > 0:
                                current_progress = min(int((current_time_ms / 1000000) / duration * 100), 99)
                                if current_progress > last_progress + 4:  # Only update if progress has changed by 5%
                                    last_progress = current_progress
                                    update_job_status(job_id, "processing", progress=current_progress)
                                    logger.info(f"Job {job_id} progress: {current_progress}%")
                except Exception as e:
                    logger.error(f"Error reading progress: {str(e)}")
                    
            # Sleep for a moment
            time.sleep(2)
        
        # Check if process completed successfully
        stdout = process.stdout.read().decode('utf-8') if process.stdout else ""
        stderr = process.stderr.read().decode('utf-8') if process.stderr else ""
        
        if process.returncode != 0:
            logger.error(f"FFmpeg process failed for job {job_id} with return code {process.returncode}")
            logger.error(f"FFmpeg stdout: {stdout}")
            logger.error(f"FFmpeg stderr: {stderr}")
            update_job_status(job_id, "failed", error_message=f"Transcoding error: {stderr[:200]}")
            return False
        
        logger.info(f"FFmpeg process completed with return code {process.returncode}")
        
        # Check if output file was actually created
        if not os.path.exists(output_path):
            logger.error(f"Output file {output_path} was not created despite process completion")
            update_job_status(job_id, "failed", error_message="Output file was not created")
            return False
            
        # Upload the transcoded file to MinIO
        try:
            logger.info(f"Uploading output file {output_path} to MinIO bucket 'transcoded' as {job_id}.{output_format}")
            minio_client.fput_object(
                "transcoded",
                f"{job_id}.{output_format}",
                output_path
            )
            logger.info(f"Successfully uploaded output file to MinIO")
        except Exception as e:
            logger.error(f"Failed to upload output file to MinIO: {str(e)}")
            update_job_status(job_id, "failed", error_message=f"Upload error: {str(e)}")
            return False
            
        logger.info(f"Transcoding job {job_id} completed successfully")
        
        # Update final status with video duration
        update_job_status(job_id, "completed", progress=100, duration=duration)
        
        # Clean up temporary files
        logger.info("Cleaning up temporary files")
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_path):
            os.remove(output_path)
        if os.path.exists(progress_file):
            os.remove(progress_file)
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg subprocess error for job {job_id}: {str(e)}")
        update_job_status(job_id, "failed", error_message=f"Transcoding error: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Error in transcoding job {job_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        update_job_status(job_id, "failed", error_message=f"Processing error: {str(e)}")
        return False
    finally:
        # Make sure we clean up even if there was an error
        for file_path in [input_path, output_path, progress_file]:
            try:
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.error(f"Error removing file {file_path}: {str(e)}")

def process_message(ch, method, properties, body):
    """
    Process a message from the RabbitMQ queue
    """
    try:
        job = json.loads(body)
        job_id = job["job_id"]
        
        logger.info(f"Received job {job_id}")
        
        # Update job status to "processing"
        update_job_status(job_id, "processing", progress=0)
        
        # Process the video
        success = transcode_video(job)
        
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