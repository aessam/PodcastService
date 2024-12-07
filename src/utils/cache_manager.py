from pathlib import Path
import json
from typing import Optional, Dict, Any
from datetime import datetime

class CacheManager:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.downloads_cache = self.cache_dir / "downloads_cache.json"
        self.transcripts_cache = self.cache_dir / "transcripts_cache.json"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize cache files if they don't exist
        self._init_cache_file(self.downloads_cache)
        self._init_cache_file(self.transcripts_cache)
    
    def _init_cache_file(self, cache_file: Path):
        """Initialize a cache file if it doesn't exist"""
        if not cache_file.exists():
            with open(cache_file, 'w') as f:
                json.dump({}, f)
    
    def _load_cache(self, cache_file: Path) -> Dict:
        """Load cache from file"""
        try:
            with open(cache_file, 'r') as f:
                return json.load(f)
        except Exception:
            return {}
    
    def _save_cache(self, cache_data: Dict, cache_file: Path):
        """Save cache to file"""
        with open(cache_file, 'w') as f:
            json.dump(cache_data, f, indent=2)
    
    def get_download_cache(self, url: str) -> Optional[Dict[str, Any]]:
        """Get cached download info for a URL"""
        cache = self._load_cache(self.downloads_cache)
        return cache.get(url)
    
    def cache_download(self, url: str, file_path: Path, metadata: Optional[Dict] = None):
        """Cache download information"""
        cache = self._load_cache(self.downloads_cache)
        cache[url] = {
            "file_path": str(file_path),
            "downloaded_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        self._save_cache(cache, self.downloads_cache)
    
    def get_transcript_cache(self, audio_path: str) -> Optional[Dict[str, Any]]:
        """Get cached transcript for an audio file"""
        cache = self._load_cache(self.transcripts_cache)
        return cache.get(audio_path)
    
    def cache_transcript(self, audio_path: str, transcript_path: Path, metadata: Optional[Dict] = None):
        """Cache transcript information"""
        cache = self._load_cache(self.transcripts_cache)
        cache[str(audio_path)] = {
            "transcript_path": str(transcript_path),
            "transcribed_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        self._save_cache(cache, self.transcripts_cache)
    
    def is_download_cached(self, url: str) -> bool:
        """Check if a URL is cached and the file exists"""
        cached = self.get_download_cache(url)
        if cached:
            file_path = Path(cached["file_path"])
            return file_path.exists()
        return False
    
    def is_transcript_cached(self, audio_path: str) -> bool:
        """Check if an audio file is transcribed and the transcript exists"""
        cached = self.get_transcript_cache(audio_path)
        if cached:
            transcript_path = Path(cached["transcript_path"])
            return transcript_path.exists()
        return False
    
    def get_cached_download_path(self, url: str) -> Optional[Path]:
        """Get the cached download path if it exists"""
        cached = self.get_download_cache(url)
        if cached:
            path = Path(cached["file_path"])
            if path.exists():
                return path
        return None
    
    def get_cached_transcript_path(self, audio_path: str) -> Optional[Path]:
        """Get the cached transcript path if it exists"""
        cached = self.get_transcript_cache(audio_path)
        if cached:
            path = Path(cached["transcript_path"])
            if path.exists():
                return path
        return None 