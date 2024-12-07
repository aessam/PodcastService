from pathlib import Path
from typing import Optional, Dict
import os
import mlx_whisper
from huggingface_hub import hf_hub_download, snapshot_download
from podcast_service.config.settings import WHISPER_MODEL_PATH

class Transcriber:
    AVAILABLE_MODELS = {
        'tiny': 'mlx-community/whisper-tiny-mlx',
        'base': 'mlx-community/whisper-base-mlx',
        'small': 'mlx-community/whisper-small-mlx',
        'medium': 'mlx-community/whisper-medium-mlx',
        'large': 'mlx-community/whisper-large-mlx',
        'large-v2': 'mlx-community/whisper-large-v2-mlx',
        'large-v3': 'mlx-community/whisper-large-v3-mlx'
    }

    def __init__(self, model_path: str = WHISPER_MODEL_PATH, user_id: Optional[str] = None, cache_manager=None):
        self.model_path = model_path
        self.user_id = user_id
        self.cache_manager = cache_manager
        self.model = self._get_model()

    def _download_model(self, model_name: str) -> str:
        """Download model from Hugging Face Hub."""
        print(f"Downloading model {model_name} from Hugging Face Hub...")
        
        # Get the full repository name
        repo_id = self.AVAILABLE_MODELS.get(model_name.lower(), model_name)
        
        # Create a local directory for the model
        local_dir = Path.home() / '.cache' / 'mlx-whisper' / model_name
        local_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Download all model files using newer API
            snapshot_download(
                repo_id=repo_id,
                local_dir=str(local_dir),
                ignore_patterns=["*.md", "*.txt"],  # Ignore documentation files
                local_dir_use_symlinks=False  # Explicitly set to False to avoid warning
            )
            print(f"Model downloaded successfully to {local_dir}")
            return str(local_dir)
        except Exception as e:
            raise RuntimeError(f"Failed to download model: {e}")

    def _get_model(self):
        """Get the model, downloading it if necessary."""
        try:
            # Check if it's one of our predefined models or a hub path
            model_name = Path(self.model_path).name.lower()
            model_dir = self.model_path
            
            # If it's a model name or hub path and not a local directory
            if not os.path.isdir(self.model_path):
                if model_name in self.AVAILABLE_MODELS or '/' in self.model_path:
                    model_dir = self._download_model(model_name)
            
            # Load the model using the correct API
            print(f"Loading model from: {model_dir}")
            return model_dir
            
        except Exception as e:
            # If loading fails, show available models and raise error
            self._show_available_models()
            raise RuntimeError(f"Failed to load Whisper model: {e}")

    def _show_available_models(self):
        """Show available MLX Whisper models."""
        print("\nAvailable MLX Whisper models:")
        for name, repo in self.AVAILABLE_MODELS.items():
            print(f"- {name}: {repo}")
        print("\nYou can either:")
        print("1. Use one of the model names above (e.g., 'large-v3')")
        print("2. Provide a path to a local model directory")
        print("3. Provide a Hugging Face model repository path")

    def get_output_path(self, audio_path: Path) -> Path:
        """Get user-specific output path for transcripts."""
        if self.user_id:
            # Use user-specific directory if user_id is provided
            base_dir = Path(os.getenv('DATA_DIR', 'data')) / self.user_id / 'transcripts'
            base_dir.mkdir(parents=True, exist_ok=True)
            return base_dir / f"{audio_path.stem}.txt"
        else:
            # Fallback to default directory
            return Path('transcripts') / f"{audio_path.stem}.txt"

    def transcribe(self, audio_path: Path) -> Optional[Dict]:
        """
        Transcribe an audio file using MLX Whisper.
        Returns the transcription result or None if transcription fails.
        """
        try:
            print(f"Transcribing {audio_path}")
            try:
                # Try the newer API
                result = self.model.transcribe(str(audio_path))
            except (AttributeError, TypeError):
                # Try the older API
                result = mlx_whisper.transcribe(
                    audio=str(audio_path),
                    path_or_hf_repo=self.model,
                    verbose=True
                )
            
            # Save transcription to user-specific directory
            transcript_path = self.get_output_path(audio_path)
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(transcript_path, 'w') as f:
                f.write(result['text'])
            
            return result
        except Exception as e:
            print(f"Error transcribing {audio_path}: {e}")
            return None

    def transcribe_multiple(self, audio_paths: list[Path]) -> list[Dict]:
        """Transcribe multiple audio files and return successful transcriptions."""
        results = []
        for path in audio_paths:
            if result := self.transcribe(path):
                results.append(result)
        return results 