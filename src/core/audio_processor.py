import subprocess
import hashlib
from pathlib import Path
from typing import Optional
import re
from podcast_service.src.core.podcast_fetcher import PodcastEpisode
from podcast_service.config.settings import DOWNLOADS_DIR

class AudioProcessor:
    def __init__(self, download_dir: Path = DOWNLOADS_DIR):
        self.download_dir = download_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _clean_filename(title: str, max_length: int = 100) -> str:
        """Clean a string to be used as a filename."""
        # Replace spaces with underscores and remove problematic characters
        clean = re.sub(r'[\\/*?:"<>|#=\-\+.]', '', title)
        clean = clean.replace(' ', '_')
        clean = clean.strip('_ ')
        return clean[:max_length]

    @staticmethod
    def _generate_hash(text: str) -> str:
        """Generate a stable hash for a string."""
        return hashlib.sha256(text.encode()).hexdigest()

    def get_audio_path(self, episode: PodcastEpisode) -> Path:
        """Generate the path where the audio file should be stored."""
        filename = self._generate_hash(self._clean_filename(episode.title))
        return self.download_dir / f"{filename}.mp3"

    def download_episode(self, episode: PodcastEpisode) -> Optional[Path]:
        """Download a podcast episode using yt-dlp."""
        output_path = self.get_audio_path(episode)
        
        if output_path.exists():
            print(f"Episode already downloaded: {episode.title}")
            return output_path

        try:
            subprocess.run(
                ['yt-dlp', '-o', str(output_path), episode.url],
                check=True,
                capture_output=True,
                text=True
            )
            if output_path.exists():
                print(f"Successfully downloaded: {episode.title}")
                return output_path
        except subprocess.CalledProcessError as e:
            print(f"Failed to download {episode.title}. Error: {e.stderr}")
            return None
        except Exception as e:
            print(f"Unexpected error downloading {episode.title}: {e}")
            return None

    def download_episodes(self, episodes: list[PodcastEpisode]) -> list[Path]:
        """Download multiple episodes and return paths to successful downloads."""
        downloaded_paths = []
        for episode in episodes:
            if path := self.download_episode(episode):
                downloaded_paths.append(path)
        return downloaded_paths 