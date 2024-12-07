> This application was entirely generated by Cursor AI. My role was limited to prompting, with minimal intervention. It took about 4 hours of iteration to shape it into its current form. The process evolved from a command-line application to a web application, incorporating user support at one point before ultimately removing it.


# Podcast Service

A Python service that downloads, transcribes, and summarizes podcast episodes using MLX Whisper and LLM-based summarization.

## Features

- Download and process individual podcast episodes or entire feeds
- Automatic episode title extraction from webpage metadata
- Transcribe audio using MLX Whisper (with automatic model download)
- Generate comprehensive summaries using LLM
- Track processed episodes to avoid duplicates
- Multiple summary formats (key ideas, concepts, quotes, etc.)
- Command-line interface for easy management
- Secure API key management using environment variables

## Project Structure

```
podcast_service/
├── config/               # Configuration settings
├── src/                 # Source code
│   ├── core/           # Core functionality
│   ├── summarization/  # Summary generation
│   ├── utils/         # Utility functions
│   └── api/           # External API integration
├── data/               # Data storage
│   ├── downloads/     # Downloaded audio files
│   ├── transcripts/   # Generated transcripts
│   └── summaries/     # Generated summaries
├── scripts/           # Utility scripts
└── tests/             # Test files
```

## Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd podcast_service
   ```

2. Create and activate conda environment:
   ```bash
   conda create -n podcast_env python=3.11 numpy=1.24 numba -y
   conda activate podcast_env
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   ```bash
   # Run the interactive setup script
   python scripts/setup_env.py
   ```

5. Start the FastAPI server:
   ```bash
   uvicorn src.api.app:app --reload
   ```
   The API will be available at `http://localhost:8000`

## Available Whisper Models

The following pre-trained models are available from MLX Hub:

- `tiny`: Smallest model, fastest but less accurate
- `base`: Good balance of speed and accuracy for simple tasks
- `small`: Better accuracy than base, still relatively fast
- `medium`: Good accuracy for most use cases
- `large`: Best accuracy, slower processing
- `large-v2`: Improved version of large model
- `large-v3`: Latest and most accurate model

You can specify the model in three ways:
1. Use a model name (e.g., `large-v3`)
2. Provide a path to a local model directory
3. Specify a custom MLX Hub model path

## Environment Variables

The following environment variables can be configured in your `.env` file:

- `OPENAI_API_KEY` (required): Your OpenAI API key
- `WHISPER_MODEL_PATH`: Model name or path (e.g., 'large-v3' or '/path/to/model')
- `LLM_MODEL` (optional): LLM model to use (default: gpt-4)
- `LLM_MAX_TOKENS` (optional): Maximum tokens for LLM (default: 4096)
- `LLM_TEMPERATURE` (optional): LLM temperature setting (default: 0.8)

## CLI Usage

The service provides a command-line interface for managing podcast feeds and processing episodes:

### Processing Individual Episodes

1. Process a single episode:
   ```bash
   # Process from webpage URL (automatically extracts title)
   python src/cli.py episode "https://example.com/podcast/episode-page"

   # Process direct audio URL with automatic title extraction from webpage
   python src/cli.py episode "https://example.com/episode.mp3"

   # Process with manual title override
   python src/cli.py episode "https://example.com/episode.mp3" --title "My Favorite Episode"
   ```

   The script will:
   - Try to extract the episode title from the webpage metadata if no title is provided
   - Fall back to the filename if title extraction fails
   - Use the provided title if specified with `--title`
   - Download the Whisper model if not available locally

### Managing Podcast Feeds

1. Add podcast feeds:
   ```bash
   python src/cli.py add https://feed1.xml https://feed2.xml
   ```

2. List configured feeds:
   ```bash
   python src/cli.py list
   ```

3. Remove feeds:
   ```bash
   python src/cli.py remove https://feed1.xml
   ```

### Processing Feed Episodes

1. Process new episodes:
   ```bash
   python src/cli.py process
   ```
   This will:
   - Download the latest episode from each feed
   - Transcribe the audio using MLX Whisper
   - Generate summaries using different templates
   - Save all outputs to the data directory

2. Force process all episodes (ignore history):
   ```bash
   python src/cli.py process --force
   ```

3. Clear processing history:
   ```bash
   python src/cli.py clear-history
   ```

### Output Structure

The service organizes outputs in the `data` directory:
- `downloads/`: Contains downloaded audio files
- `transcripts/`: Contains episode transcripts
- `summaries/`: Contains generated summaries in different formats:
  - `key_ideas.md`: Main points from the episode
  - `concepts.md`: Detailed concept breakdown
  - `quotes.md`: Notable quotes
  - `actionable_items.md`: Action items and takeaways
  - `experimental.md`: Experimental summary format

## Python API Usage

You can also use the service programmatically:

```python
from src.core.podcast_fetcher import PodcastFetcher, PodcastEpisode
from src.core.audio_processor import AudioProcessor
from src.core.transcriber import Transcriber
from src.summarization.summarizer import Summarizer
from datetime import datetime

# Initialize with specific model
transcriber = Transcriber(model_path='large-v3')  # Will download if needed

# Process a single episode
episode = PodcastEpisode(
    title="Episode Title",
    url="https://example.com/episode.mp3",
    published_date=datetime.now(),
    description="",
    podcast_name="Direct URL"
)

processor = AudioProcessor()
summarizer = Summarizer()

# Process the episode
audio_path = processor.download_episode(episode)
transcription = transcriber.transcribe(audio_path)
summary = summarizer.generate_summary(transcription['text'])
summarizer.save_summary(summary, audio_path.stem)

# Or process multiple episodes from feeds
fetcher = PodcastFetcher()
episodes = fetcher.get_latest_episodes(['feed_url1', 'feed_url2'])
audio_paths = processor.download_episodes(episodes)
transcriptions = transcriber.transcribe_multiple(audio_paths)

for trans in transcriptions:
    summary = summarizer.generate_summary(trans['text'])
    summarizer.save_summary(summary, trans['audio_path'].stem)
```

## Security Notes

1. Never commit your `.env` file to version control
2. Keep your API keys secure and rotate them regularly
3. The `.gitignore` file is configured to exclude sensitive files
4. Use environment variables for all sensitive information

## Dependencies

- feedparser: RSS feed parsing
- yt-dlp: Audio download
- mlx-whisper: Audio transcription
- langchain: LLM integration
- openai: OpenAI API client
- python-dotenv: Environment variable management
- beautifulsoup4: HTML parsing for title extraction
- requests: HTTP client for webpage fetching

## API Usage

The service provides a FastAPI-based REST API for managing podcasts and processing episodes:

### API Endpoints

1. Access the interactive API documentation:
   ```
   http://localhost:8000/docs
   ```
   This provides a Swagger UI interface to test all available endpoints.

2. Alternative API documentation:
   ```
   http://localhost:8000/redoc
   ```
   This provides a ReDoc interface for API documentation.