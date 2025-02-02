from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from typing import Optional, Dict, List
from pathlib import Path
import os
import json
import urllib.parse
import logging

from podcast_service.src.core.service import PodcastService
from podcast_service.config.settings import DATA_DIR

app = FastAPI(title="Podcast Service API")

# Mount static files
static_dir = Path(__file__).parent.parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize service
service = PodcastService(Path(DATA_DIR))

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

@app.get("/api/summary/{url:path}")
async def get_summary(url: str):
    try:
        # Decode URL
        decoded_url = urllib.parse.unquote(url)
        
        # Get history
        history = service.get_history()
        
        # Find the episode
        episode = next((ep for ep in history if ep['url'] == decoded_url), None)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        
        # Check if summary exists
        if not episode.get('summary'):
            # Try to generate summary if transcript exists
            if episode.get('transcript_path') and Path(episode['transcript_path']).exists():
                try:
                    with open(episode['transcript_path'], 'r', encoding='utf-8') as f:
                        transcript_text = f.read()
                    
                    # Generate summary
                    summary = service._generate_structured_summary(transcript_text)
                    if summary:
                        # Save summary
                        file_hash = service._generate_file_hash(decoded_url)
                        summary_path = service.summaries_dir / f"{file_hash}_summary.json"
                        with open(summary_path, 'w', encoding='utf-8') as f:
                            json.dump(summary, f, indent=2)
                        
                        # Update history entry
                        episode['summary_path'] = str(summary_path)
                        episode['has_summary'] = True
                        episode['summary'] = summary
                        
                        # Save updated history
                        service._save_to_history(episode)
                        
                        return {"summary": summary}
                except Exception as e:
                    print(f"Error generating summary: {e}")
                    pass
            
            raise HTTPException(status_code=404, detail="Summary not found")
        
        # Load summary
        try:
            with open(episode['summary_path'], 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            return {"summary": summary_data}
        except Exception as e:
            print(f"Error reading summary file: {e}")
            raise HTTPException(status_code=500, detail="Error reading summary file")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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

@app.get("/api/transcript/{url:path}")
async def get_transcript(url: str):
    try:
        # Decode URL
        decoded_url = urllib.parse.unquote(url)
        
        # Get history
        history = service.get_history()
        
        # Find the episode
        episode = next((ep for ep in history if ep['url'] == decoded_url), None)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        
        # Check if transcript exists
        if not episode.get('transcript_path') or not Path(episode['transcript_path']).exists():
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Load transcript
        try:
            with open(episode['transcript_path'], 'r', encoding='utf-8') as f:
                transcript_text = f.read()
            return {"transcript": transcript_text}
        except Exception as e:
            print(f"Error reading transcript file: {e}")
            raise HTTPException(status_code=500, detail="Error reading transcript file")
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting transcript: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 

@app.post("/api/generate_summary/{url:path}")
async def generate_summary(
    url: str,
    background_tasks: BackgroundTasks
):
    try:
        # Decode URL
        decoded_url = urllib.parse.unquote(url)
        
        # Get history
        history = service.get_history()
        
        # Find the episode
        episode = next((ep for ep in history if ep['url'] == decoded_url), None)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        
        # Check if transcript exists
        if not episode.get('transcript_path') or not Path(episode['transcript_path']).exists():
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Start summary generation in background
        async def generate_summary_task():
            try:
                # Read transcript
                with open(episode['transcript_path'], 'r', encoding='utf-8') as f:
                    transcript_text = f.read()
                
                # Generate summary
                summary = service._generate_structured_summary(transcript_text)
                if not summary:
                    print("Failed to generate summary")
                    return
                
                # Save summary
                file_hash = service._generate_file_hash(decoded_url)
                summary_path = service.summaries_dir / f"{file_hash}_summary.json"
                with open(summary_path, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, indent=2)
                
                # Update history entry
                episode['summary_path'] = str(summary_path)
                episode['has_summary'] = True
                episode['summary'] = summary
                
                # Save updated history
                service._save_to_history(episode)
                
            except Exception as e:
                print(f"Error in summary generation task: {e}")
        
        background_tasks.add_task(generate_summary_task)
        
        return {"message": "Summary generation started"}
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error starting summary generation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 

@app.get("/api/tts/playlist/{episode_id}")
async def get_tts(episode_id: str):
    try:
        logger.info(f"Generating TTS for episode: {episode_id}")
        
        # Generate TTS for summary sections
        tts_paths = service.get_summary_tts(episode_id)
        if not tts_paths:
            logger.warning(f"No TTS paths found for episode: {episode_id}")
            raise HTTPException(status_code=404, detail="TTS not found")
        
        logger.debug(f"Generated TTS paths: {tts_paths}")
        
        # Create a list of all audio files with their sections
        audio_files = []
        
        # Add comprehensive summary first
        if tts_paths.get('comprehensive_summary'):
            paths = tts_paths['comprehensive_summary'] if isinstance(tts_paths['comprehensive_summary'], list) else [tts_paths['comprehensive_summary']]
            for path in paths:
                audio_files.append({
                    "filename": Path(path).name,
                    "section": "Summary",
                    "url": f"/api/tts/audio/{Path(path).name}"
                })
        
        # Add key insights
        if tts_paths.get('key_insights'):
            paths = tts_paths['key_insights'] if isinstance(tts_paths['key_insights'], list) else [tts_paths['key_insights']]
            for path in paths:
                audio_files.append({
                    "filename": Path(path).name,
                    "section": "Key Insights",
                    "url": f"/api/tts/audio/{Path(path).name}"
                })
        
        # Add action items
        if tts_paths.get('action_items'):
            paths = tts_paths['action_items'] if isinstance(tts_paths['action_items'], list) else [tts_paths['action_items']]
            for path in paths:
                audio_files.append({
                    "filename": Path(path).name,
                    "section": "Action Items",
                    "url": f"/api/tts/audio/{Path(path).name}"
                })
        
        # Add wisdom
        if tts_paths.get('wisdom'):
            paths = tts_paths['wisdom'] if isinstance(tts_paths['wisdom'], list) else [tts_paths['wisdom']]
            for path in paths:
                audio_files.append({
                    "filename": Path(path).name,
                    "section": "Wisdom",
                    "url": f"/api/tts/audio/{Path(path).name}"
                })
        
        logger.info(f"Returning {len(audio_files)} audio files")
        return {"audio_files": audio_files}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting TTS: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tts/audio/{filename:path}")
async def get_tts_audio(filename: str):
    try:
        logger.info(f"Serving audio file: {filename}")
        audio_path = Path(DATA_DIR) / "tts" / filename
        
        if not audio_path.exists():
            logger.warning(f"Audio file not found: {audio_path}")
            raise HTTPException(status_code=404, detail="Audio file not found")
        
        logger.debug(f"Serving file from path: {audio_path}")
        
        # Determine content type based on extension
        if filename.endswith('.m3u'):
            media_type = 'application/vnd.apple.mpegurl'
            # For M3U files, serve from the tts directory
            return FileResponse(
                str(audio_path),
                media_type=media_type,
                filename=filename
            )
        else:
            media_type = 'audio/mpeg'
            return FileResponse(
                str(audio_path),
                media_type=media_type,
                filename=filename
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving audio file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 

@app.post("/api/episode/refresh-metadata/{url:path}")
async def refresh_metadata(url: str):
    try:
        # Decode URL
        decoded_url = urllib.parse.unquote(url)
        metadata = service.refresh_episode_metadata(decoded_url)
        return metadata
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 

@app.get("/api/search/podcasts")
async def search_podcasts(q: str = None):
    """Search for podcasts using iTunes API"""
    print(f"Received search request with query: {q}")
    try:
        if not q:
            raise HTTPException(status_code=400, detail="Query parameter 'q' is required")
        print(f"Searching for podcasts with query: {q}")
        results = service.search_podcasts(q)
        print(f"Found {len(results)} results")
        return results
    except Exception as e:
        print(f"Error searching podcasts: {e}")
        return {"error": str(e)}

@app.post("/api/subscribe/podcast")
async def subscribe_to_podcast(data: Dict):
    """Subscribe to a podcast"""
    try:
        success = service.subscribe_to_podcast(data['id'], data['feed_url'])
        if success:
            return {"status": "success"}
        raise HTTPException(status_code=400, detail="Failed to subscribe")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/subscribe/youtube")
async def subscribe_to_youtube(data: Dict):
    """Subscribe to a YouTube channel"""
    try:
        success = service.subscribe_to_youtube(data['url'])
        if success:
            return {"status": "success"}
        raise HTTPException(status_code=400, detail="Failed to subscribe")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/refresh-episodes")
async def refresh_episodes():
    """Refresh episodes for all subscriptions"""
    try:
        episodes = service.refresh_episodes()
        return {
            'podcast': episodes.get('podcast', []),
            'youtube': episodes.get('youtube', [])
        }
    except Exception as e:
        logger.error(f"Error refreshing episodes: {e}", exc_info=True)
        return {'podcast': [], 'youtube': []}

@app.get("/api/subscriptions")
async def get_subscriptions():
    """Get all subscriptions"""
    try:
        return service.cache_manager.get_all_subscriptions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 

@app.post("/api/re_summarize/{episode_id}")
async def re_summarize(
    episode_id: str,
    language: dict,
    background_tasks: BackgroundTasks
):
    try:
        # Get history
        history = service.get_history()
        
        # Find the episode
        episode = next((ep for ep in history if ep['id'] == episode_id), None)
        if not episode:
            raise HTTPException(status_code=404, detail="Episode not found")
        
        # Check if transcript exists
        if not episode.get('transcript_path') or not Path(episode['transcript_path']).exists():
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Start summary generation in background
        async def generate_summary_task():
            try:
                # Read transcript
                with open(episode['transcript_path'], 'r', encoding='utf-8') as f:
                    transcript_text = f.read()
                
                # Generate summary in specified language
                summary = service._generate_structured_summary(transcript_text, target_language=language.get('language', 'en'))
                if not summary:
                    print("Failed to generate summary")
                    return
                
                # Save summary
                file_hash = service._generate_file_hash(episode['url'])
                summary_path = service.summaries_dir / f"{file_hash}_summary_{language.get('language', 'en')}.json"
                with open(summary_path, 'w', encoding='utf-8') as f:
                    json.dump(summary, f, indent=2)
                
                # Update history entry
                episode['summary_path'] = str(summary_path)
                episode['has_summary'] = True
                episode['summary'] = summary
                episode['summary_language'] = language.get('language', 'en')
                
                # Save updated history
                service._save_to_history(episode)
                
            except Exception as e:
                print(f"Error in summary generation task: {e}")
        
        background_tasks.add_task(generate_summary_task)
        
        return {"message": "Summary generation started"}
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error starting summary generation: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 