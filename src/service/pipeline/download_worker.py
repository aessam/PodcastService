import time
from multiprocessing import Process, current_process
from pathlib import Path
import logging
import uuid
import sys
import traceback

from ...core.service import PodcastService
from ...core.podcast_fetcher import PodcastFetcher
from ...core.transcriber import Transcriber
from ...summarization.summarizer import Summarizer
from ..queue.in_memory_queue import ProcessingQueue, JobStatus, PodcastJob

# Configure logging for the worker process
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class DownloadWorker(Process):
    def __init__(self, data_dir: Path = Path("data")):
        super().__init__()
        self.data_dir = data_dir
        self.running = True
        self.name = f"DownloadWorker-{uuid.uuid4().hex[:8]}"
        # Queue will be initialized in the worker process
        self.queue = None

    def run(self):
        """Main worker loop"""
        try:
            process = current_process()
            logger.info(f"Starting worker process {self.name} (PID: {process.pid})")
            
            # Initialize queue in worker process
            logger.info("Initializing queue in worker process")
            self.queue = ProcessingQueue()
            
            # Initialize other services
            logger.info("Initializing services...")
            self.podcast_service = PodcastService(self.data_dir)
            self.podcast_fetcher = PodcastFetcher()
            self.transcriber = Transcriber()
            self.summarizer = Summarizer(output_dir=self.data_dir / "summaries")
            
            logger.info(f"Worker {self.name} initialized successfully")
            
            job_check_count = 0
            while self.running:
                try:
                    job_check_count += 1
                    if job_check_count % 10 == 0:  # Log every 10th check
                        logger.info(f"Worker {self.name} checking for jobs... (check #{job_check_count})")
                    else:
                        logger.debug(f"Worker {self.name} checking for jobs...")
                        
                    job = self.queue.get_job()
                    if job:
                        logger.info(f"Worker {self.name} processing job {job.job_id}")
                        try:
                            if job.is_feed:
                                self._process_feed(job)
                            else:
                                self._process_single_episode(job)
                            logger.info(f"Worker {self.name} completed job {job.job_id}")
                        except Exception as e:
                            logger.error(f"Error processing job {job.job_id}: {str(e)}\n{traceback.format_exc()}")
                            self.queue.update_job_status(job.job_id, JobStatus.FAILED, str(e))
                    else:
                        if job_check_count % 10 == 0:  # Log every 10th check
                            logger.info(f"Worker {self.name} found no jobs, waiting...")
                        else:
                            logger.debug(f"Worker {self.name} found no jobs, waiting...")
                except Exception as e:
                    logger.error(f"Error in worker loop: {str(e)}\n{traceback.format_exc()}")
                
                time.sleep(1)  # Prevent busy waiting
                
        except Exception as e:
            logger.error(f"Fatal error in worker process: {str(e)}\n{traceback.format_exc()}")
            raise
        finally:
            logger.info(f"Worker {self.name} shutting down")

    def _process_feed(self, job: PodcastJob):
        """Process a podcast feed URL"""
        logger.info(f"Processing feed: {job.url}")
        self.queue.update_job_status(job.job_id, JobStatus.DOWNLOADING)
        
        # Fetch episodes from feed
        episodes = self.podcast_fetcher.fetch_episodes(job.url)
        job.episode_count = len(episodes)
        logger.info(f"Found {len(episodes)} episodes in feed")
        
        if not episodes:
            raise Exception("No episodes found in feed")
        
        # Create a job for each episode
        for episode in episodes:
            episode_job = PodcastJob(
                job_id=str(uuid.uuid4()),
                url=episode['audio_url'],
                is_feed=False
            )
            episode_job.title = episode['title']
            episode_job.description = episode['description']
            episode_job.published_date = episode['published']
            episode_job.duration = episode['duration']
            episode_job.feed_metadata = {
                'feed_url': job.url,
                'parent_job_id': job.job_id
            }
            
            self.queue.add_job(episode_job)
            logger.info(f"Created job for episode: {episode_job.title}")
        
        # Update feed job status
        job.feed_metadata = {
            'total_episodes': len(episodes),
            'processed_episodes': 0
        }
        self.queue.update_job_status(job.job_id, JobStatus.COMPLETED)
        logger.info(f"Completed feed processing: {job.url}")

    def _process_single_episode(self, job: PodcastJob):
        """Process a single podcast episode"""
        try:
            # Download phase
            logger.info(f"Starting download for: {job.url}")
            self.queue.update_job_status(job.job_id, JobStatus.DOWNLOADING)
            if job.title:
                download_path = self.podcast_fetcher.download_episode(job.url, job.title)
            else:
                download_result = self.podcast_service.download_podcast(job.url)
                download_path = download_result.get("file_path")
                job.title = download_result.get("title")
                job.duration = download_result.get("duration")
            
            if not download_path:
                raise Exception("Failed to download episode")
            
            job.download_path = str(download_path)
            logger.info(f"Downloaded episode to {job.download_path}")
            
            # Transcription phase
            logger.info(f"Starting transcription for: {job.title}")
            self.queue.update_job_status(job.job_id, JobStatus.TRANSCRIBING)
            transcript_result = self.transcriber.transcribe(Path(job.download_path))
            if not transcript_result:
                raise Exception("Failed to transcribe episode")
            
            transcript_path = self.transcriber.get_output_path(Path(job.download_path))
            job.transcript_path = str(transcript_path)
            logger.info(f"Transcribed episode to {job.transcript_path}")
            
            # Summarization phase
            logger.info(f"Starting summarization for: {job.title}")
            self.queue.update_job_status(job.job_id, JobStatus.SUMMARIZING)
            with open(transcript_path, 'r') as f:
                transcript_text = f.read()
            
            summary = self.summarizer.generate_summary(transcript_text)
            if not summary:
                raise Exception("Failed to generate summary")
            
            summary_path = self.summarizer.save_summary(
                summary,
                f"{Path(job.download_path).stem}_summary"
            )
            job.summary_path = summary_path
            logger.info(f"Generated summary at {job.summary_path}")
            
            # Update final status
            self.queue.update_job_status(job.job_id, JobStatus.COMPLETED)
            logger.info(f"Completed processing for: {job.title}")
            
            # Update parent feed job if this is part of a feed
            if job.feed_metadata and 'parent_job_id' in job.feed_metadata:
                parent_status = self.queue.get_job_status(job.feed_metadata['parent_job_id'])
                if parent_status:
                    parent_status['feed_metadata']['processed_episodes'] += 1
                    self.queue.job_statuses[job.feed_metadata['parent_job_id']] = parent_status
                    logger.info(f"Updated parent feed progress: {parent_status['feed_metadata']}")
                    
        except Exception as e:
            logger.error(f"Error processing episode {job.job_id}: {str(e)}", exc_info=True)
            self.queue.update_job_status(job.job_id, JobStatus.FAILED, str(e))

    def stop(self):
        """Stop the worker"""
        logger.info(f"Stopping worker {self.name}")
        self.running = False