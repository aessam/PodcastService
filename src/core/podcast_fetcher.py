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
    def __init__(self, download_dir: Path, cache_manager=None):
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.cache_manager = cache_manager
        self._last_download_metadata = None  # Store metadata from last download

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

    def get_download_metadata(self) -> Optional[Dict]:
        """Get metadata from the last download."""
        return self._last_download_metadata

    def download_episode(self, url: str, title: Optional[str] = None) -> Optional[Path]:
        """Download a podcast episode with caching"""
        # Reset metadata for new download
        self._last_download_metadata = None

        # Check cache first if cache manager is available
        if self.cache_manager and self.cache_manager.is_download_cached(url):
            print(f"Using cached download for: {title or url}")
            return self.cache_manager.get_cached_download_path(url)

        # First extract metadata without downloading if no title provided
        extracted_title = None
        if not title:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # Only extract metadata
            }

            try:
                # First get metadata
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if isinstance(info, dict):
                        extracted_title = info.get("title")
                        if not extracted_title:
                            extracted_title = info.get("webpage_title")
                    else:
                        print(f"Warning: Unexpected metadata format: {type(info)}")
            except Exception as e:
                print(f"Warning: Could not extract metadata: {e}")

        # Now download with the best available title
        display_title = title or extracted_title or url
        safe_filename = "".join(c for c in display_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        download_opts = {
            'format': 'bestaudio/best',
            'outtmpl': str(self.download_dir / f"{safe_filename}.%(ext)s"),
            'quiet': True,
            'no_warnings': True,
            'extract_audio': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
            }],
        }

        try:
            print(f"Downloading episode: {display_title}")
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not isinstance(info, dict):
                    raise ValueError(f"Unexpected download info format: {type(info)}")
                
                filename = ydl.prepare_filename(info)
                # Convert the filename to .wav since we're extracting audio
                wav_path = Path(filename).with_suffix('.wav')
                
                if not wav_path.exists():
                    raise ValueError(f"Expected audio file not found: {wav_path}")
                
                # Store metadata for later retrieval
                self._last_download_metadata = {
                    "title": display_title,
                    "duration": info.get("duration"),
                    "description": info.get("description"),
                    "webpage_url": info.get("webpage_url"),
                    "uploader": info.get("uploader"),
                }
                
                # Cache the download if cache manager is available
                if self.cache_manager:
                    self.cache_manager.cache_download(url, wav_path, self._last_download_metadata)
                
                return wav_path
        except Exception as e:
            print(f"Error downloading episode: {e}")
            return None