from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional, Dict, List
from pathlib import Path
import os

from podcast_service.src.core.service import PodcastService
from podcast_service.config.settings import DATA_DIR

app = FastAPI(title="Podcast Service API")

# Mount static files
static_dir = Path(__file__).parent.parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize service
service = PodcastService(Path(DATA_DIR))

# Serve index.html at root
@app.get("/")
async def read_root():
    return FileResponse(str(static_dir / "index.html"))

# Background task to process episode
def process_episode_task(url: str, title: Optional[str] = None):
    try:
        result = service.process_episode(url, title)
        return result
    except Exception as e:
        print(f"Error processing episode: {e}")
        return None

# API Routes
@app.get("/api/settings")
async def get_settings():
    return service.get_settings()

@app.post("/api/settings")
async def update_settings(settings: dict):
    if service.update_settings(settings):
        return {"message": "Settings updated successfully"}
    raise HTTPException(status_code=400, detail="Failed to update settings")

@app.post("/api/process/episode")
async def process_episode(
    background_tasks: BackgroundTasks,
    url: str,
    title: Optional[str] = None,
    request: Request = None
):
    if not url:
        raise HTTPException(status_code=422, detail="URL is required")
    
    try:
        # Start processing in background
        background_tasks.add_task(
            process_episode_task,
            url=url,
            title=title
        )
        
        return {
            "message": "Processing started",
            "url": url,
            "title": title
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/history")
async def get_history():
    return service.get_history() 