from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from typing import List, Optional
import uvicorn
from pathlib import Path
import json
import urllib.parse

from podcast_service.src.core.service import PodcastService
from podcast_service.src.core.user import User
from podcast_service.config.settings import DATA_DIR, TRANSCRIPTS_DIR, SUMMARIES_DIR

# Initialize FastAPI app
app = FastAPI(
    title="Podcast Service API",
    description="API for podcast downloading, transcription, and summarization",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Initialize service
service = PodcastService(Path(DATA_DIR))

# Static files configuration
static_dir = Path(__file__).parent.parent.parent / "static"
app.mount("/js", StaticFiles(directory=str(static_dir / "js")), name="javascript")

@app.get("/")
async def read_root():
    return FileResponse(str(static_dir / "index.html"))

# Background task to process episode
def process_episode_task(url: str, title: Optional[str] = None, user_id: Optional[str] = None):
    try:
        if user_id:
            service.current_user = service.user_manager.get_user(user_id)
        result = service.process_episode(url, title)
        return result
    except Exception as e:
        print(f"Error processing episode: {e}")
        return None

# API Routes
@app.post("/api/register")
async def register_user(username: str, email: str, password: str):
    try:
        user = service.register_user(username, email, password)
        return {"message": "User registered successfully", "user_id": user.user_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/login")
async def login_user(username: str, password: str):
    if service.login(username, password):
        return {
            "message": "Login successful",
            "user": service.current_user.to_dict()
        }
    raise HTTPException(status_code=401, detail="Invalid credentials")

@app.post("/api/logout")
async def logout_user():
    service.logout()
    return {"message": "Logged out successfully"}

@app.get("/api/user/settings")
async def get_user_settings():
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return service.get_user_settings()

@app.post("/api/user/settings")
async def update_user_settings(settings: dict):
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    if service.update_user_settings(settings):
        return {"message": "Settings updated successfully"}
    raise HTTPException(status_code=400, detail="Failed to update settings")

@app.post("/api/process/episode")
async def process_episode(
    background_tasks: BackgroundTasks,
    url: str,
    title: Optional[str] = None,
    request: Request = None
):
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    if not url:
        raise HTTPException(status_code=422, detail="URL is required")
    
    try:
        # Start processing in background
        background_tasks.add_task(
            process_episode_task,
            url=url,
            title=title,
            user_id=service.current_user.user_id
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
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    return service.get_user_history()

@app.get("/api/files/transcript/{url:path}")
async def get_transcript(url: str):
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    try:
        # Handle double-encoded URLs
        decoded_url = urllib.parse.unquote(urllib.parse.unquote(url))
        
        history = service.get_user_history()
        # Find the episode in history
        episode = next((ep for ep in history if ep['url'] == decoded_url), None)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        
        transcript_path = Path(episode.get('transcript_path', ''))
        if not transcript_path or not transcript_path.exists():
            raise HTTPException(status_code=404, detail="Transcript file not found")
        
        try:
            # Read the transcript file
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_text = f.read()
            return {"transcript": transcript_text}
        except Exception as e:
            print(f"Error reading transcript: {e}")
            raise HTTPException(status_code=500, detail=f"Error reading transcript: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing transcript request: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.get("/api/files/summary/{url:path}")
async def get_summary(url: str):
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    try:
        # Handle double-encoded URLs
        decoded_url = urllib.parse.unquote(urllib.parse.unquote(url))
        
        history = service.get_user_history()
        # Find the episode in history
        episode = next((ep for ep in history if ep['url'] == decoded_url), None)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        
        if not episode.get('summary_path'):
            raise HTTPException(status_code=404, detail="No summary available for this episode")
        
        summary_path = Path(episode['summary_path'])
        if not summary_path.is_file():
            raise HTTPException(status_code=404, detail="Summary file not found")
        
        try:
            # Read the summary file
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
                
            # Return the actual summary text
            if isinstance(summary_data, dict) and 'summary' in summary_data:
                return {"summary": summary_data['summary']}
            else:
                raise HTTPException(status_code=500, detail="Invalid summary data format")
                
        except json.JSONDecodeError as e:
            print(f"Error decoding summary file {summary_path}: {e}")
            raise HTTPException(status_code=500, detail="Error decoding summary file")
        except Exception as e:
            print(f"Error reading summary file {summary_path}: {e}")
            raise HTTPException(status_code=500, detail=f"Error reading summary: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error processing summary request: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.get("/api/status/{task_id}")
async def get_task_status(task_id: str):
    # TODO: Implement task status tracking
    return {"status": "pending"}

@app.post("/api/tts/generate")
async def generate_tts(text: str, filename: str):
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    try:
        audio_path = service.generate_tts(text, filename)
        if not audio_path:
            raise HTTPException(status_code=500, detail="Failed to generate TTS")
        
        return {"audio_path": audio_path}
    except Exception as e:
        print(f"Error generating TTS: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tts/{filename:path}")
async def get_tts_audio(filename: str):
    if not service.current_user:
        raise HTTPException(status_code=401, detail="Not logged in")
    
    try:
        # Get user-specific TTS directory
        tts_dir = service.data_dir / service.current_user.user_id / "tts"
        audio_path = tts_dir / filename
        
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        return FileResponse(
            str(audio_path),
            media_type="audio/mpeg",
            filename=filename
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error serving TTS audio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True) 