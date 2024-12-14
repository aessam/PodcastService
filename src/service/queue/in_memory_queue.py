from multiprocessing import Queue, Manager
from typing import Any, Dict, List, Optional
from enum import Enum
import threading
import time

class JobStatus(Enum):
    IN_QUEUE = "in_queue"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"

class PodcastJob:
    def __init__(self, job_id: str, url: str):
        self.job_id = job_id
        self.url = url
        self.status = JobStatus.IN_QUEUE
        self.error = None
        self.created_at = time.time()
        self.updated_at = time.time()
        # Additional metadata
        self.download_path = None
        self.transcript_path = None
        self.summary_path = None
        self.language = None
        self.duration = None
        self.title = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "status": self.status.value,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "download_path": self.download_path,
            "transcript_path": self.transcript_path,
            "summary_path": self.summary_path,
            "language": self.language,
            "duration": self.duration,
            "title": self.title
        }

class ProcessingQueue:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ProcessingQueue, cls).__new__(cls)
                    cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.manager = Manager()
        self.job_queue = Queue()
        self.job_statuses = self.manager.dict()  # Shared dict for job statuses

    def add_job(self, job: PodcastJob) -> str:
        """Add a new job to the queue"""
        self.job_statuses[job.job_id] = {
            "status": job.status.value,
            "url": job.url,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "error": None
        }
        self.job_queue.put(job)
        return job.job_id

    def get_job(self) -> Optional[PodcastJob]:
        """Get the next job from the queue"""
        try:
            return self.job_queue.get_nowait()
        except:
            return None

    def update_job_status(self, job_id: str, status: JobStatus, error: str = None):
        """Update the status of a job"""
        if job_id in self.job_statuses:
            job_data = self.job_statuses[job_id]
            job_data["status"] = status.value
            job_data["error"] = error
            job_data["updated_at"] = time.time()
            self.job_statuses[job_id] = job_data

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get the status of a specific job"""
        return self.job_statuses.get(job_id)

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs and their statuses"""
        return [
            {"job_id": job_id, **job_data}
            for job_id, job_data in self.job_statuses.items()
        ] 