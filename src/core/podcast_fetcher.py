import feedparser
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import yt_dlp

class PodcastFetcher:
    def __init__(self):
        self.downloads_dir = Path("data/downloads")
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    def fetch_episodes(self, feed_url: str) -> List[Dict]:
        """Fetch episodes from a podcast feed"""
        try:
            feed = feedparser.parse(feed_url)
            episodes = []
            
            for entry in feed.entries:
                episode = {
                    'id': entry.get('id', ''),
                    'title': entry.get('title', ''),
                    'description': entry.get('description', ''),
                    'published': entry.get('published', ''),
                    'audio_url': self._get_audio_url(entry),
                    'duration': entry.get('itunes_duration', ''),
                    'image': entry.get('image', {}).get('href', ''),
                    'link': entry.get('link', ''),
                    'feed_url': feed_url,
                    'processed': False
                }
                if episode['audio_url']:
                    episodes.append(episode)
            
            return episodes
        except Exception as e:
            print(f"Error fetching podcast episodes: {e}")
            return []

    def download_episode(self, url: str, title: str = None) -> Optional[Path]:
        """Download a podcast episode"""
        try:
            # Generate a safe filename from the title or URL
            safe_filename = "".join(c for c in (title or url) if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_filename = safe_filename[:100]  # Limit filename length
            
            # Add timestamp to ensure uniqueness
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.downloads_dir / f"{safe_filename}_{timestamp}.mp3"
            
            # Download using yt-dlp
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': str(output_path),
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            return output_path if output_path.exists() else None
        except Exception as e:
            print(f"Error downloading episode: {e}")
            return None

    def _get_audio_url(self, entry) -> str:
        """Extract audio URL from feed entry"""
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.type and 'audio' in enclosure.type:
                    return enclosure.href
        return ''