from pathlib import Path
from typing import Optional, Dict, List
import os
from datetime import datetime
import json

from podcast_service.src.core.transcriber import Transcriber
from podcast_service.src.core.podcast_fetcher import PodcastFetcher
from podcast_service.src.summarization.summarizer import Summarizer
from podcast_service.src.utils.cache_manager import CacheManager
from openai import OpenAI
import io

class PodcastService:
    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize OpenAI client
        self.openai_client = OpenAI()
        
        # Initialize cache manager
        self.cache_manager = CacheManager(self.data_dir / "cache")
        
        # Load settings
        self.settings = self._load_settings()
        
        # Initialize components as None
        self.transcriber: Optional[Transcriber] = None
        
        # Create necessary directories
        self.downloads_dir = self.data_dir / "downloads"
        self.transcripts_dir = self.data_dir / "transcripts"
        self.summaries_dir = self.data_dir / "summaries"
        
        for directory in [self.downloads_dir, self.transcripts_dir, self.summaries_dir]:
            directory.mkdir(parents=True, exist_ok=True)
    
    def _get_settings_file(self) -> Path:
        return self.data_dir / "settings.json"
    
    def _get_history_file(self) -> Path:
        return self.data_dir / "history.json"
    
    def _load_settings(self) -> Dict:
        """Load settings if exists, otherwise return defaults"""
        settings_file = self._get_settings_file()
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Default settings
        return {
            "default_model": "base",
            "output_format": "txt",
            "auto_summarize": True
        }
    
    def _save_settings(self):
        """Save current settings"""
        with open(self._get_settings_file(), 'w') as f:
            json.dump(self.settings, f)
    
    def _initialize_transcriber(self):
        """Initialize transcriber with current settings if not already initialized"""
        if self.transcriber is None:
            self.transcriber = Transcriber(
                model_path=self.settings.get("default_model", "base"),
                cache_manager=self.cache_manager
            )
    
    def get_settings(self) -> Dict:
        """Get current settings"""
        return self.settings
    
    def update_settings(self, settings: Dict) -> bool:
        """Update settings"""
        self.settings.update(settings)
        self._save_settings()
        return True
    
    def process_episode(self, url: str, title: Optional[str] = None) -> Dict:
        """Process a single podcast episode"""
        # Initialize components
        fetcher = PodcastFetcher(self.downloads_dir, cache_manager=self.cache_manager)
        self._initialize_transcriber()
        summarizer = Summarizer(self.summaries_dir)
        
        try:
            # Step 1: Download or get cached audio
            print(f"\n{'='*50}")
            print(f"Processing episode: {title or url}")
            print(f"{'='*50}")
            
            print("\n[Step 1/3] Audio Processing")
            print("-" * 20)
            audio_path = None
            if self.cache_manager.is_download_cached(url):
                print("✓ Using cached audio file")
                audio_path = self.cache_manager.get_cached_download_path(url)
            else:
                print("⌛ Downloading audio...")
                audio_path = fetcher.download_episode(url, title)
                print("✓ Download complete")
            
            if not audio_path:
                raise RuntimeError("Failed to get audio file")
            
            # Step 2: Transcribe or get cached transcript
            print("\n[Step 2/3] Transcription")
            print("-" * 20)
            transcript = None
            transcript_path = None
            if self.cache_manager.is_transcript_cached(str(audio_path)):
                print("✓ Using cached transcript")
                transcript_path = self.cache_manager.get_cached_transcript_path(str(audio_path))
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    transcript_text = f.read()
                transcript = {"text": transcript_text}
            else:
                print("⌛ Transcribing audio (this may take a while)...")
                transcript = self.transcriber.transcribe(audio_path)
                transcript_path = self.transcriber.get_output_path(audio_path)
                print("✓ Transcription complete")
            
            if not transcript:
                raise RuntimeError("Failed to get transcript")
            
            # Step 3: Generate summary if enabled
            print("\n[Step 3/3] Summarization")
            print("-" * 20)
            summary = None
            summary_path = None
            if self.settings.get("auto_summarize", True):
                cached_summary_path = self.summaries_dir / f"{audio_path.stem}.json"
                if cached_summary_path.exists():
                    print("✓ Using cached summary")
                    with open(cached_summary_path, 'r', encoding='utf-8') as f:
                        summary_data = json.load(f)
                        summary = summary_data.get("summary")
                        summary_path = cached_summary_path
                else:
                    print("⌛ Generating summary (this may take several minutes)...")
                    summary = summarizer.generate_summary(transcript['text'])
                    if summary:
                        summary_path = Path(summarizer.save_summary(summary, audio_path.stem))
                        print("✓ Summary generation complete")
                    else:
                        print("⚠ Summary generation failed")
            else:
                print("ℹ Summarization skipped (disabled in settings)")
            
            # Create result object
            print("\nFinalizing results...")
            result = {
                "url": url,
                "title": title or audio_path.stem,
                "audio_path": str(audio_path),
                "transcript_path": str(transcript_path),
                "summary_path": str(summary_path) if summary_path else None,
                "processed_at": datetime.utcnow().isoformat(),
                "duration": transcript.get("duration", 0),
                "has_summary": bool(summary)
            }
            
            # Save to history
            self._save_to_history(result)
            
            print("\n✓ Processing complete!")
            print(f"{'='*50}\n")
            
            return result
            
        except Exception as e:
            print("\n⚠ Error during processing!")
            print(f"Error: {e}")
            raise RuntimeError(f"Failed to process episode: {e}")
    
    def get_history(self) -> List[Dict]:
        """Get processing history"""
        try:
            history_file = self._get_history_file()
            if not history_file.exists():
                return []
            
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            # Validate file paths exist
            for entry in history:
                if 'transcript_path' in entry:
                    transcript_path = Path(entry['transcript_path'])
                    if not transcript_path.exists():
                        entry['transcript_path'] = None
                
                if 'summary_path' in entry:
                    summary_path = Path(entry['summary_path'])
                    if not summary_path.exists():
                        entry['summary_path'] = None
            
            return history
        except json.JSONDecodeError:
            print("Error decoding history file")
            return []
        except Exception as e:
            print(f"Error reading history: {e}")
            return []
    
    def _save_to_history(self, result: Dict):
        """Save processing result to history"""
        try:
            history_file = self._get_history_file()
            
            # Load existing history
            history = []
            if history_file.exists():
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Error reading existing history: {e}")
            
            # Add new result to history
            history.append(result)
            
            # Save updated history
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")
            raise RuntimeError(f"Failed to save processing history: {e}")