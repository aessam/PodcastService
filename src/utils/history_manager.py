import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from podcast_service.config.settings import HISTORY_FILE

class HistoryManager:
    def __init__(self, history_file: Path = HISTORY_FILE):
        self.history_file = history_file
        self.history: Dict[str, Any] = self._load_history()

    def _load_history(self) -> Dict[str, Any]:
        """Load history from file or create new if doesn't exist."""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Error reading history file {self.history_file}")
                return {}
        return {}

    def _save_history(self) -> None:
        """Save history to file."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2, default=str)

    def add_episode(self, url: str, metadata: Dict[str, Any]) -> None:
        """Add a processed episode to history."""
        self.history[url] = {
            **metadata,
            'processed_at': datetime.now().isoformat()
        }
        self._save_history()

    def get_episode(self, url: str) -> Optional[Dict[str, Any]]:
        """Get episode history if it exists."""
        return self.history.get(url)

    def is_processed(self, url: str) -> bool:
        """Check if an episode has been processed."""
        return url in self.history

    def clear_history(self) -> None:
        """Clear all history."""
        self.history = {}
        self._save_history()

    def remove_episode(self, url: str) -> None:
        """Remove an episode from history."""
        if url in self.history:
            del self.history[url]
            self._save_history() 