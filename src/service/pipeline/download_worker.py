import time
from multiprocessing import Process
from pathlib import Path
import logging

from ...core.service import PodcastService
from ..queue.in_memory_queue import ProcessingQueue, JobStatus

logger = logging.getLogger(__name__)

class DownloadWorker(Process):
    def __init__(self, data_dir: Path = Path("data")):
        super().__init__()
        self.queue = ProcessingQueue()
        self.running = True
        self.data_dir = data_dir
        self.podcast_service = None  # Initialize in run() since it needs to be in the new process

    def run(self):
        """Main worker loop"""
        # Initialize PodcastService in the worker process
        self.podcast_service = PodcastService(self.data_dir)
        
        while self.running:
            job = self.queue.get_job()
            if job:
                try:
                    # Download phase
                    self.queue.update_job_status(job.job_id, JobStatus.DOWNLOADING)
                    download_result = self.podcast_service.download_podcast(job.url)
                    job.download_path = str(download_result.get("file_path"))
                    job.title = download_result.get("title")
                    job.duration = download_result.get("duration")
                    
                    # Transcription phase
                    self.queue.update_job_status(job.job_id, JobStatus.TRANSCRIBING)
                    transcript_result = self.podcast_service.transcribe_audio(job.download_path)
                    job.transcript_path = str(transcript_result.get("transcript_path"))
                    job.language = transcript_result.get("language")
                    
                    # Summarization phase
                    self.queue.update_job_status(job.job_id, JobStatus.SUMMARIZING)
                    summary_result = self.podcast_service.summarize_transcript(job.transcript_path)
                    job.summary_path = str(summary_result.get("summary_path"))
                    
                    # Update final status
                    self.queue.update_job_status(job.job_id, JobStatus.COMPLETED)
                    
                except Exception as e:
                    logger.error(f"Error processing job {job.job_id}: {str(e)}")
                    self.queue.update_job_status(job.job_id, JobStatus.FAILED, str(e))
            
            time.sleep(1)  # Prevent busy waiting

    def stop(self):
        """Stop the worker"""
        self.running = False 