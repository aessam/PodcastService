from pathlib import Path
from typing import Optional, Dict, List
import os
from datetime import datetime
import json
import hashlib

from podcast_service.src.core.user import UserManager, User
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
        
        # Initialize managers
        self.user_manager = UserManager(self.data_dir)
        self.current_user: Optional[User] = None
        self.cache_manager = CacheManager(self.data_dir / "cache")
        
        # Load session if exists
        self._load_session()
        
        # Initialize components as None
        self.transcriber: Optional[Transcriber] = None
    
    def _get_session_file(self) -> Path:
        return self.data_dir / "session.json"
    
    def _save_session(self):
        """Save current user session"""
        if self.current_user:
            session_data = self.current_user.to_dict()
            with open(self._get_session_file(), 'w') as f:
                json.dump(session_data, f)
        else:
            # Remove session file if exists
            session_file = self._get_session_file()
            if session_file.exists():
                session_file.unlink()
    
    def _load_session(self):
        """Load user session if exists"""
        session_file = self._get_session_file()
        if session_file.exists():
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)
                    self.current_user = User.from_dict(session_data)
            except Exception:
                # If session is corrupted, remove it
                session_file.unlink()
                self.current_user = None
    
    def _initialize_transcriber(self):
        """Initialize transcriber with current user settings if not already initialized"""
        if not self.current_user:
            raise ValueError("No user logged in")
            
        if self.transcriber is None:
            self.transcriber = Transcriber(
                model_path=self.current_user.settings.get("default_model", "base"),
                user_id=self.current_user.user_id,
                cache_manager=self.cache_manager
            )
    
    def register_user(self, username: str, email: str, password: str) -> User:
        """Register a new user"""
        user = self.user_manager.create_user(username, email, password)
        self.current_user = user
        self._save_session()
        return user
    
    def login(self, username: str, password: str) -> bool:
        """Log in a user"""
        user = self.user_manager.authenticate_user(username, password)
        if user:
            self.current_user = user
            self._save_session()
            return True
        return False
    
    def logout(self):
        """Log out the current user"""
        self.current_user = None
        self._save_session()
    
    def get_user_settings(self) -> Optional[Dict]:
        """Get current user's settings"""
        if self.current_user:
            return self.current_user.settings
        return None
    
    def update_user_settings(self, settings: Dict) -> bool:
        """Update current user's settings"""
        if self.current_user:
            return self.user_manager.update_user_settings(self.current_user.user_id, settings)
        return False
    
    def process_episode(self, url: str, title: Optional[str] = None) -> Dict:
        """Process a single podcast episode"""
        if not self.current_user:
            raise ValueError("No user logged in")
        
        # Get user-specific directories
        user_dir = self.data_dir / self.current_user.user_id
        downloads_dir = user_dir / "downloads"
        transcripts_dir = user_dir / "transcripts"
        summaries_dir = user_dir / "summaries"
        
        # Create directories if they don't exist
        for directory in [downloads_dir, transcripts_dir, summaries_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Initialize components with user-specific paths
        fetcher = PodcastFetcher(downloads_dir, cache_manager=self.cache_manager)
        self._initialize_transcriber()  # Initialize or reuse transcriber
        summarizer = Summarizer(summaries_dir)
        
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
            if self.current_user.settings.get("auto_summarize", True):
                cached_summary_path = summaries_dir / f"{audio_path.stem}.json"
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
                        # Save summary and get the path
                        summary_path = Path(summarizer.save_summary(summary, audio_path.stem))
                        print("✓ Summary generation complete")
                    else:
                        print("⚠ Summary generation failed")
            else:
                print("ℹ Summarization skipped (disabled in settings)")
            
            # Create result object
            print("\nFinalizing results...")
            result = {
                "user_id": self.current_user.user_id,
                "url": url,
                "title": title or audio_path.stem,
                "audio_path": str(audio_path),
                "transcript_path": str(transcript_path),
                "summary_path": str(summary_path) if summary_path else None,
                "processed_at": datetime.utcnow().isoformat(),
                "duration": transcript.get("duration", 0),
                "has_summary": bool(summary)
            }
            
            # Save processing history
            self._save_processing_history(result)
            
            print("\n✓ Processing complete!")
            print(f"{'='*50}\n")
            
            return result
            
        except Exception as e:
            print("\n⚠ Error during processing!")
            print(f"Error: {e}")
            raise RuntimeError(f"Failed to process episode: {e}")
    
    def get_user_history(self) -> List[Dict]:
        """Get the user's processing history"""
        if not self.current_user:
            raise ValueError("No user logged in")
        
        try:
            history_file = self.data_dir / self.current_user.user_id / "history.json"
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
            print(f"Error decoding history file for user {self.current_user.user_id}")
            return []
        except Exception as e:
            print(f"Error reading history for user {self.current_user.user_id}: {e}")
            return []
    
    def _save_processing_history(self, result: Dict):
        """Save processing result to user's history"""
        if not self.current_user:
            raise ValueError("No user logged in")
        
        try:
            history_file = self.data_dir / self.current_user.user_id / "history.json"
            history_file.parent.mkdir(parents=True, exist_ok=True)
            
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
    
    def process_feeds(self, feeds: List[str], force: bool = False) -> List[Dict]:
        """Process latest episodes from podcast feeds"""
        if not self.current_user:
            raise ValueError("No user logged in")
        
        # Get user-specific directories
        user_dir = self.data_dir / self.current_user.user_id
        downloads_dir = user_dir / "downloads"
        
        # Initialize components with user-specific paths
        fetcher = PodcastFetcher(downloads_dir, cache_manager=self.cache_manager)
        self._initialize_transcriber()  # Initialize transcriber once
        
        # Get latest episodes from all feeds
        results = []
        history = self.get_user_history() if not force else []
        processed_urls = {entry['url'] for entry in history}
        
        for feed_url in feeds:
            try:
                # Get only the latest episode
                episode = fetcher.get_latest_episode(feed_url)
                if not episode:
                    print(f"No episodes found in feed: {feed_url}")
                    continue
                
                # Process the episode
                print(f"\nProcessing latest episode from {episode.podcast_name}:")
                print(f"Title: {episode.title}")
                result = self.process_episode(episode.url, episode.title)
                results.append(result)
                
            except Exception as e:
                print(f"Error processing feed {feed_url}: {e}")
        
        return results 
    
    def _generate_tts_filename(self, text: str, base_filename: str) -> str:
        """Generate a unique filename for TTS based on content and base filename"""
        # Create a hash of the text content
        content_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        # Create a safe base filename
        safe_base = Path(base_filename).stem
        # Combine them for a unique filename
        return f"{safe_base}_{content_hash}"
    
    def generate_tts(self, text: str, filename: str) -> Optional[str]:
        """Generate text-to-speech audio using OpenAI's API"""
        if not self.current_user:
            raise ValueError("No user logged in")
        
        try:
            # Get user-specific audio directory
            user_dir = self.data_dir / self.current_user.user_id
            tts_dir = user_dir / "tts"
            tts_dir.mkdir(parents=True, exist_ok=True)
            
            # Create unique output path based on content
            unique_filename = self._generate_tts_filename(text, filename)
            output_path = tts_dir / f"{unique_filename}.mp3"
            
            # Check if audio already exists
            if output_path.exists():
                return str(output_path)
            
            # Generate TTS using OpenAI
            response = self.openai_client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=text
            )
            
            # Save the audio file
            response.stream_to_file(str(output_path))
            
            return str(output_path)
            
        except Exception as e:
            print(f"Error generating TTS: {e}")
            return None