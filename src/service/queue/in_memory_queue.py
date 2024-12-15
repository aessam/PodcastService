from multiprocessing import Queue, Manager
from typing import Any, Dict, List, Optional
from enum import Enum
import threading
import time
import logging
import json
from pathlib import Path
import os

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    IN_QUEUE = "in_queue"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    SUMMARIZING = "summarizing"
    COMPLETED = "completed"
    FAILED = "failed"

class PodcastJob:
    def __init__(self, job_id: str, url: str, is_feed: bool = False):
        self.job_id = job_id
        self.url = url
        self.is_feed = is_feed
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
        # Feed specific metadata
        self.feed_metadata = None
        self.episode_count = None
        self.feed_title = None
        self.description = None
        self.published_date = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PodcastJob':
        """Create a PodcastJob instance from a dictionary"""
        job = cls(data['job_id'], data['url'], data.get('is_feed', False))
        job.status = JobStatus(data['status'])
        job.error = data.get('error')
        job.created_at = data.get('created_at', time.time())
        job.updated_at = data.get('updated_at', time.time())
        job.download_path = data.get('download_path')
        job.transcript_path = data.get('transcript_path')
        job.summary_path = data.get('summary_path')
        job.language = data.get('language')
        job.duration = data.get('duration')
        job.title = data.get('title')
        job.feed_metadata = data.get('feed_metadata')
        job.episode_count = data.get('episode_count')
        job.feed_title = data.get('feed_title')
        job.description = data.get('description')
        job.published_date = data.get('published_date')
        return job

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "is_feed": self.is_feed,
            "status": self.status.value,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "download_path": self.download_path,
            "transcript_path": self.transcript_path,
            "summary_path": self.summary_path,
            "language": self.language,
            "duration": self.duration,
            "title": self.title,
            "feed_metadata": self.feed_metadata,
            "episode_count": self.episode_count,
            "feed_title": self.feed_title,
            "description": self.description,
            "published_date": self.published_date
        }

class ProcessingQueue:
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    _QUEUE_FILE = "data/queue/job_queue.json"
    _HISTORY_FILE = "data/queue/job_history.json"

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ProcessingQueue, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._initialize()
                    ProcessingQueue._initialized = True

    def _initialize(self):
        """Initialize shared resources and load persisted data"""
        logger.info("Initializing ProcessingQueue...")
        self.manager = Manager()
        self.job_queue = self.manager.Queue()
        self.job_statuses = self.manager.dict()

        # Create queue directory if it doesn't exist
        os.makedirs(os.path.dirname(self._QUEUE_FILE), exist_ok=True)
        os.makedirs(os.path.dirname(self._HISTORY_FILE), exist_ok=True)

        # Load persisted data
        self._load_persisted_data()
        logger.info("ProcessingQueue initialized successfully")

    def _load_persisted_data(self):
        """Load job data from files"""
        try:
            # Load job statuses
            if os.path.exists(self._HISTORY_FILE):
                with open(self._HISTORY_FILE, 'r') as f:
                    history_data = json.load(f)
                    for job_id, job_data in history_data.items():
                        self.job_statuses[job_id] = job_data

            # Load queue
            if os.path.exists(self._QUEUE_FILE):
                with open(self._QUEUE_FILE, 'r') as f:
                    queue_data = json.load(f)
                    for job_data in queue_data:
                        job = PodcastJob.from_dict(job_data)
                        if job.status == JobStatus.IN_QUEUE:
                            self.job_queue.put(job)

            logger.info("Loaded persisted queue data successfully")
        except Exception as e:
            logger.error(f"Error loading persisted data: {e}")

    def _save_queue_state(self):
        """Save current queue state to file"""
        try:
            # Save job statuses
            with open(self._HISTORY_FILE, 'w') as f:
                json.dump(dict(self.job_statuses), f, indent=2)

            # Save current queue
            queue_data = []
            try:
                while True:
                    job = self.job_queue.get_nowait()
                    queue_data.append(job.to_dict())
                    self.job_queue.put(job)  # Put it back
            except:
                pass

            with open(self._QUEUE_FILE, 'w') as f:
                json.dump(queue_data, f, indent=2)

            logger.debug("Saved queue state successfully")
        except Exception as e:
            logger.error(f"Error saving queue state: {e}")

    def add_job(self, job: PodcastJob) -> str:
        """Add a new job to the queue"""
        logger.info(f"Adding job {job.job_id} to queue")
        with self._lock:
            # Store job status
            self.job_statuses[job.job_id] = job.to_dict()
            # Put the job in the queue
            self.job_queue.put(job)
            # Save state
            self._save_queue_state()
            logger.info(f"Job {job.job_id} added successfully")
            return job.job_id

    def get_job(self) -> Optional[PodcastJob]:
        """Get the next job from the queue"""
        try:
            logger.debug("Attempting to get job from queue")
            job = self.job_queue.get_nowait()
            logger.info(f"Retrieved job {job.job_id} from queue")
            self._save_queue_state()  # Save state after removing job from queue
            return job
        except Exception as e:
            logger.debug(f"No job available in queue: {str(e)}")
            return None

    def update_job_status(self, job_id: str, status: JobStatus, error: str = None):
        """Update the status of a job"""
        logger.info(f"Updating job {job_id} status to {status.value}")
        with self._lock:
            if job_id in self.job_statuses:
                job_data = self.job_statuses[job_id]
                job_data["status"] = status.value
                job_data["error"] = error
                job_data["updated_at"] = time.time()
                self.job_statuses[job_id] = job_data
                # Save state after updating status
                self._save_queue_state()
                logger.info(f"Job {job_id} status updated successfully")
            else:
                logger.warning(f"Job {job_id} not found in status dictionary")

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Get the status of a specific job"""
        return self.job_statuses.get(job_id)

    def get_all_jobs(self) -> List[Dict[str, Any]]:
        """Get all jobs and their statuses"""
        return [
            {"job_id": job_id, **job_data}
            for job_id, job_data in self.job_statuses.items()
        ]