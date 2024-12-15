from pathlib import Path
from typing import Optional, List, Dict
import logging
from multiprocessing import Process, current_process, active_children
import time
import uuid
import threading
import atexit
import sys

from ...core.service import PodcastService
from ..queue.in_memory_queue import ProcessingQueue, JobStatus, PodcastJob
from .download_worker import DownloadWorker

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class ServiceManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, data_dir: Path = Path("data")):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ServiceManager, cls).__new__(cls)
                    cls._instance._initialize(data_dir)
        return cls._instance

    def _initialize(self, data_dir: Path):
        """Initialize the service manager"""
        self.data_dir = data_dir
        self.queue = ProcessingQueue()  # Initialize queue in main process
        self.workers = []
        self._started = False
        self._main_pid = current_process().pid
        self._worker_check_thread = None
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
        
    def _cleanup(self):
        """Cleanup method for atexit"""
        if current_process().pid == self._main_pid:
            logger.info("Running cleanup...")
            self.stop_workers()
    
    def _check_workers(self):
        """Periodically check worker health and restart if needed"""
        while self._started:
            try:
                # Get all active child processes
                active_processes = active_children()
                active_pids = {p.pid for p in active_processes}
                
                # Check each worker
                for worker in self.workers[:]:  # Copy list to allow modification
                    if not worker.is_alive() or worker.pid not in active_pids:
                        logger.warning(f"Worker {worker.name} (PID: {worker.pid}) is not running, restarting...")
                        self.workers.remove(worker)
                        new_worker = DownloadWorker(self.data_dir)
                        new_worker.start()
                        self.workers.append(new_worker)
                        logger.info(f"Started new worker {new_worker.name} (PID: {new_worker.pid})")
            except Exception as e:
                logger.error(f"Error in worker check thread: {e}", exc_info=True)
            
            time.sleep(5)  # Check every 5 seconds
        
    def start_workers(self):
        """Start all worker processes if not already started"""
        with self._lock:
            if self._started:
                logger.info("Workers already started")
                return
            
            try:
                logger.info("Starting workers...")
                # Start download worker
                download_worker = DownloadWorker(self.data_dir)
                download_worker.start()
                self.workers.append(download_worker)
                self._started = True
                logger.info(f"Started download worker (PID: {download_worker.pid})")
                
                # Start worker check thread
                self._worker_check_thread = threading.Thread(target=self._check_workers)
                self._worker_check_thread.daemon = True
                self._worker_check_thread.start()
                logger.info("Started worker monitoring thread")
                
            except Exception as e:
                logger.error(f"Error starting workers: {e}", exc_info=True)
                self.stop_workers()
                raise
        
    def stop_workers(self):
        """Stop all worker processes if running"""
        with self._lock:
            if not self._started:
                logger.info("Workers already stopped")
                return
            
            logger.info("Stopping all workers...")
            self._started = False  # This will stop the check thread
            
            if self._worker_check_thread and self._worker_check_thread.is_alive():
                self._worker_check_thread.join(timeout=5)
            
            for worker in self.workers:
                try:
                    if worker.is_alive():
                        logger.info(f"Stopping worker {worker.name} (PID: {worker.pid})")
                        worker.stop()
                        worker.join(timeout=5)
                        if worker.is_alive():
                            logger.warning(f"Worker {worker.name} did not stop gracefully, terminating...")
                            worker.terminate()
                except Exception as e:
                    logger.error(f"Error stopping worker: {e}", exc_info=True)
            
            self.workers = []
            logger.info("All workers stopped")
        
    def process_podcast(self, url: str, is_feed: bool = False) -> str:
        """Add a new podcast to the processing queue"""
        if not self._started:
            logger.warning("Workers not started, starting now...")
            self.start_workers()
        
        job = PodcastJob(job_id=str(uuid.uuid4()), url=url, is_feed=is_feed)
        job_id = self.queue.add_job(job)
        logger.info(f"Added {'feed' if is_feed else 'episode'} {url} to queue with job ID {job_id}")
        
        # Verify workers are running
        active_workers = [w for w in self.workers if w.is_alive()]
        logger.info(f"Active workers: {len(active_workers)}")
        if not active_workers:
            logger.warning("No active workers found, restarting workers...")
            self.stop_workers()
            self.start_workers()
        
        return job_id
        
    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Get the status of a specific job"""
        return self.queue.get_job_status(job_id)
        
    def get_processing_history(self) -> List[Dict]:
        """Get the history of all processed jobs"""
        return self.queue.get_all_jobs()
    
    def get_feed_episodes(self, feed_job_id: str) -> Optional[List[Dict]]:
        """Get all episodes associated with a feed job"""
        feed_status = self.queue.get_job_status(feed_job_id)
        if not feed_status or not feed_status.get('is_feed'):
            return None
        
        # Find all episodes with this feed as parent
        episodes = []
        for job in self.queue.get_all_jobs():
            if (job.get('feed_metadata') and 
                job['feed_metadata'].get('parent_job_id') == feed_job_id):
                episodes.append(job)
        
        return sorted(episodes, key=lambda x: x.get('created_at', 0))