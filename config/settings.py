import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(env_path)

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
SUMMARIES_DIR = DATA_DIR / "summaries"

# MLX Whisper settings
WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH")
if not WHISPER_MODEL_PATH:
    raise ValueError("WHISPER_MODEL_PATH environment variable is not set. Please check your .env file.")

# API Keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY environment variable is not set. Please check your .env file.")

# LLM Settings
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.8"))

# History settings
HISTORY_FILE = DATA_DIR / "summary_history.json"

# Create directories if they don't exist
for dir_path in [DOWNLOADS_DIR, TRANSCRIPTS_DIR, SUMMARIES_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True) 