from pathlib import Path
import json
from typing import Optional, Dict, Any
from datetime import datetime
import hashlib
import shutil

class CacheManager:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_cache = self.cache_dir / "downloads"
        self.downloads_cache.mkdir(exist_ok=True)
        self.transcripts_cache = self.cache_dir / "transcripts"
        self.transcripts_cache.mkdir(exist_ok=True)
        self.metadata_cache = self.cache_dir / "metadata"
        self.metadata_cache.mkdir(exist_ok=True)

    def _get_cache_key(self, key: str) -> str:
        """Generate a stable cache key."""
        return hashlib.sha256(key.encode()).hexdigest()

    def get_download_metadata(self, url: str) -> Optional[Dict]:
        """Get metadata for a cached download."""
        cache_key = self._get_cache_key(url)
        metadata_path = self.metadata_cache / f"{cache_key}.json"
        
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error reading metadata cache: {e}")
                return None
        return None

    def cache_download(self, url: str, file_path: Path, metadata: Optional[Dict] = None) -> None:
        """Cache a downloaded file and its metadata."""
        cache_key = self._get_cache_key(url)
        cache_path = self.downloads_cache / f"{cache_key}{file_path.suffix}"
        
        # Cache the file
        shutil.copy2(file_path, cache_path)
        
        # Cache metadata if provided
        if metadata:
            metadata_path = self.metadata_cache / f"{cache_key}.json"
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

    def get_cached_download_path(self, url: str) -> Optional[Path]:
        """Get path to cached download if it exists."""
        cache_key = self._get_cache_key(url)
        # Try common audio extensions
        for ext in ['.wav', '.mp3', '.m4a']:
            cache_path = self.downloads_cache / f"{cache_key}{ext}"
            if cache_path.exists():
                return cache_path
        return None

    def is_download_cached(self, url: str) -> bool:
        """Check if a download is cached."""
        return bool(self.get_cached_download_path(url))

    def cache_transcript(self, audio_path: str, transcript_path: Path) -> None:
        """Cache a transcript file."""
        cache_key = self._get_cache_key(audio_path)
        cache_path = self.transcripts_cache / f"{cache_key}.txt"
        shutil.copy2(transcript_path, cache_path)

    def get_cached_transcript_path(self, audio_path: str) -> Optional[Path]:
        """Get path to cached transcript if it exists."""
        cache_key = self._get_cache_key(audio_path)
        cache_path = self.transcripts_cache / f"{cache_key}.txt"
        return cache_path if cache_path.exists() else None

    def is_transcript_cached(self, audio_path: str) -> bool:
        """Check if a transcript is cached."""
        return bool(self.get_cached_transcript_path(audio_path)) 