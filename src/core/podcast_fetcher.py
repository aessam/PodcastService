import feedparser
from typing import List, Dict
from datetime import datetime

class PodcastFetcher:
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
                    'duration': entry.get('itunes_duration', '')
                }
                episodes.append(episode)
            
            return episodes
        except Exception as e:
            print(f"Error fetching podcast episodes: {e}")
            return []

    def _get_audio_url(self, entry) -> str:
        """Extract audio URL from feed entry"""
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.type and 'audio' in enclosure.type:
                    return enclosure.href
        return ''