from fastapi import APIRouter, HTTPException
from typing import Optional
from pathlib import Path
from pydantic import BaseModel
import logging

from ...service.pipeline.service_manager import ServiceManager

# Configure logging
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/queue", tags=["queue"])

# Initialize service manager (but don't start workers yet)
service_manager = ServiceManager(Path("data"))

# Request models
class ProcessRequest(BaseModel):
    url: str
    is_feed: bool = False

# Response models
class ProcessResponse(BaseModel):
    job_id: str
    status: str
    message: str

@router.post("/process", response_model=ProcessResponse)
async def process_podcast(request: ProcessRequest):
    """Queue a podcast or feed for processing"""
    try:
        job_id = service_manager.process_podcast(request.url, request.is_feed)
        return ProcessResponse(
            job_id=job_id,
            status="queued",
            message=f"{'Feed' if request.is_feed else 'Episode'} processing has been queued"
        )
    except Exception as e:
        logger.error(f"Error processing podcast: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{job_id}")
async def get_status(job_id: str):
    """Get the status of a specific job"""
    try:
        status = service_manager.get_job_status(job_id)
        if not status:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Add progress info for feeds
        if status.get('is_feed') and status.get('feed_metadata'):
            total = status['feed_metadata'].get('total_episodes', 0)
            processed = status['feed_metadata'].get('processed_episodes', 0)
            status['progress'] = {
                'total_episodes': total,
                'processed_episodes': processed,
                'percentage': (processed / total * 100) if total > 0 else 0
            }
        
        return status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_history():
    """Get processing history"""
    try:
        jobs = service_manager.get_processing_history()
        
        # Group episodes under their parent feeds
        organized_jobs = []
        feed_jobs = {}
        
        for job in jobs:
            if job.get('is_feed'):
                feed_jobs[job['job_id']] = job
                job['episodes'] = []
                organized_jobs.append(job)
            elif job.get('feed_metadata') and job['feed_metadata'].get('parent_job_id') in feed_jobs:
                parent_id = job['feed_metadata']['parent_job_id']
                feed_jobs[parent_id]['episodes'].append(job)
            else:
                organized_jobs.append(job)
        
        return {
            'jobs': organized_jobs,
            'total': len(organized_jobs)
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/feed/{job_id}/episodes")
async def get_feed_episodes(job_id: str):
    """Get all episodes for a specific feed"""
    try:
        episodes = service_manager.get_feed_episodes(job_id)
        if episodes is None:
            raise HTTPException(status_code=404, detail="Feed job not found")
        
        return {
            'episodes': episodes,
            'total': len(episodes)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting feed episodes: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 