from pathlib import Path
from typing import Optional
import logging
from multiprocessing import Process
import time
import uuid

from ...core.service import PodcastService
from ..queue.in_memory_queue import ProcessingQueue, JobStatus, PodcastJob
from .download_worker import DownloadWorker

logger = logging.getLogger(__name__)

class ServiceManager:
    def __init__(self, data_dir: Path = Path("data")):
        self.podcast_service = PodcastService(data_dir)
        self.queue = ProcessingQueue()
        self.workers = []
        
    def start_workers(self):
        """Start all worker processes"""
        # Start download worker
        download_worker = DownloadWorker()
        download_worker.start()
        self.workers.append(download_worker)
        logger.info("Started download worker")
        
    def stop_workers(self):
        """Stop all worker processes"""
        for worker in self.workers:
            worker.stop()
            worker.join()
        self.workers = []
        logger.info("Stopped all workers")
        
    def process_podcast(self, url: str) -> str:
        """Add a new podcast to the processing queue"""
        job = PodcastJob(job_id=str(uuid.uuid4()), url=url)
        job_id = self.queue.add_job(job)
        logger.info(f"Added podcast {url} to queue with job ID {job_id}")
        return job_id
        
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get the status of a specific job"""
        return self.queue.get_job_status(job_id)
        
    def get_processing_history(self):
        """Get the history of all processed jobs"""
        return self.queue.get_all_jobs() 