import feedparser
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import yt_dlp

@dataclass
class PodcastEpisode:
    title: str
    url: str
    published_date: datetime
    description: str
    podcast_name: str

class PodcastFetcher:
    def __init__(self, download_dir: Optional[Path] = None, cache_manager=None):
        self.download_dir = Path(download_dir) if download_dir else Path("downloads")
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.cache_manager = cache_manager

    def get_latest_episode(self, feed_url: str) -> Optional[PodcastEpisode]:
        """Get only the latest episode from a podcast feed"""
        episodes = self.get_feed_episodes(feed_url)
        return episodes[0] if episodes else None

    def get_feed_episodes(self, feed_url: str) -> List[PodcastEpisode]:
        """Get episodes from a podcast feed"""
        feed = feedparser.parse(feed_url)
        episodes = []

        # Sort entries by published date if available
        entries = sorted(
            feed.entries,
            key=lambda e: tuple(e.get('published_parsed', (0,)*9))[:6],
            reverse=True
        )

        for entry in entries:
            # Find the audio URL
            audio_url = None
            for link in entry.get('links', []):
                if link.get('type', '').startswith('audio/'):
                    audio_url = link['href']
                    break
            
            if not audio_url:
                # Try to find enclosure
                if hasattr(entry, 'enclosures') and entry.enclosures:
                    for enclosure in entry.enclosures:
                        if enclosure.get('type', '').startswith('audio/'):
                            audio_url = enclosure.get('href')
                            break

            if audio_url:
                # Parse the published date
                published = entry.get('published_parsed')
                if published:
                    published_date = datetime(*published[:6])
                else:
                    published_date = datetime.now()

                episode = PodcastEpisode(
                    title=entry.get('title', 'Unknown Title'),
                    url=audio_url,
                    published_date=published_date,
                    description=entry.get('summary', ''),
                    podcast_name=feed.feed.get('title', 'Unknown Podcast')
                )
                episodes.append(episode)

        return episodes

    def download_episode(self, url: str, title: Optional[str] = None) -> Optional[Path]:
        """Download a podcast episode with caching"""
        # Check cache first if cache manager is available
        if self.cache_manager and self.cache_manager.is_download_cached(url):
            print(f"Using cached download for: {title or url}")
            return self.cache_manager.get_cached_download_path(url)

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(self.download_dir / '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'extract_audio': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
        }

        try:
            print(f"Downloading episode: {title or url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                # Convert the filename to .wav since we're extracting audio
                wav_path = Path(filename).with_suffix('.wav')
                
                # Cache the download if cache manager is available
                if self.cache_manager:
                    self.cache_manager.cache_download(url, wav_path, {
                        "title": title or info.get("title"),
                        "duration": info.get("duration")
                    })
                
                return wav_path
        except Exception as e:
            print(f"Error downloading episode: {e}")
            return None 