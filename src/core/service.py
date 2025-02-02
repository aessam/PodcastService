from pathlib import Path
from typing import Optional, Dict, List, Union
import os
from datetime import datetime
import json
import uuid
import hashlib
import logging
from langdetect import detect, DetectorFactory
import yt_dlp
import requests
import traceback

from podcast_service.src.core.transcriber import Transcriber
from podcast_service.src.core.podcast_fetcher import PodcastFetcher
from podcast_service.src.summarization.summarizer import Summarizer
from podcast_service.src.utils.cache_manager import CacheManager
from openai import OpenAI
import io
from tiktoken import get_encoding, encoding_for_model

logger = logging.getLogger(__name__)

# Set seed for consistent language detection
DetectorFactory.seed = 0

class PodcastService:
    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized PodcastService with data directory: {data_dir}")
        
        # Initialize OpenAI client
        self.openai_client = OpenAI()
        
        # Initialize cache manager
        self.cache_manager = CacheManager(self.data_dir / "cache")
        
        # Initialize podcast fetcher
        self.podcast_fetcher = PodcastFetcher()
        
        # Load settings
        self.settings = self._load_settings()
        
        # Initialize components as None
        self.transcriber: Optional[Transcriber] = None
        
        # Create necessary directories
        self.downloads_dir = self.data_dir / "downloads"
        self.transcripts_dir = self.data_dir / "transcripts"
        self.summaries_dir = self.data_dir / "summaries"
        
        for directory in [self.downloads_dir, self.transcripts_dir, self.summaries_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Get model from environment
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4")  # Use existing LLM_MODEL from config
        self.llm_max_tokens = int(os.getenv("LLM_MAX_TOKENS", "32000"))
        self.llm_temperature = float(os.getenv("LLM_TEMPERATURE", "0.8"))
        logger.info(f"Using LLM model: {self.llm_model} with max tokens: {self.llm_max_tokens}")
    
    def _get_settings_file(self) -> Path:
        return self.data_dir / "settings.json"
    
    def _get_history_file(self) -> Path:
        return self.data_dir / "history.json"
    
    def _load_settings(self) -> Dict:
        """Load settings if exists, otherwise return defaults"""
        settings_file = self._get_settings_file()
        if settings_file.exists():
            try:
                with open(settings_file, 'r') as f:
                    return json.load(f)
            except Exception:
                pass
        
        # Default settings
        return {
            "default_model": "base",
            "output_format": "txt",
            "auto_summarize": True
        }
    
    def _save_settings(self):
        """Save current settings"""
        with open(self._get_settings_file(), 'w') as f:
            json.dump(self.settings, f)
    
    def _initialize_transcriber(self):
        """Initialize transcriber with current settings if not already initialized"""
        if self.transcriber is None:
            self.transcriber = Transcriber(
                model_path=self.settings.get("default_model", "base"),
                cache_manager=self.cache_manager
            )
    
    def get_settings(self) -> Dict:
        """Get current settings"""
        return self.settings
    
    def update_settings(self, settings: Dict) -> bool:
        """Update settings"""
        self.settings.update(settings)
        self._save_settings()
        return True
    
    def _chunk_text(self, text: str, max_chunk_size: int) -> List[str]:
        """Split text into chunks of roughly equal size, trying to break at sentence boundaries"""
        logger.info(f"Chunking text with max size: {max_chunk_size} characters")
        
        # Remove extra whitespace but preserve some paragraph breaks
        text = '\n'.join(' '.join(line.split()) for line in text.split('\n') if line.strip())
        
        # Get token count for the entire text
        total_tokens = self._estimate_tokens(text)
        logger.info(f"Total tokens in text: {total_tokens}")
        
        # If text is within token limit, return it as is
        if total_tokens <= 120000:  # Using 120k as safe limit for 128k context
            logger.info("Text is within token limit, returning as single chunk")
            return [text]
        
        # Calculate optimal chunk size in tokens
        # Aim for chunks of about 100k tokens to leave room for system prompts and response
        target_tokens = 100000
        optimal_chunks = (total_tokens + target_tokens - 1) // target_tokens
        optimal_token_size = total_tokens // optimal_chunks
        
        logger.info(f"Total tokens: {total_tokens}, Optimal chunks: {optimal_chunks}, Target tokens per chunk: {optimal_token_size}")
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        # First try to split by paragraphs
        paragraphs = text.split('\n')
        
        for paragraph in paragraphs:
            # Estimate tokens for this paragraph
            paragraph_tokens = self._estimate_tokens(paragraph)
            
            # If single paragraph exceeds chunk size, split it into sentences
            if paragraph_tokens > optimal_token_size:
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Split paragraph into sentences
                sentences = []
                current = []
                
                words = paragraph.split()
                for i, word in enumerate(words):
                    current.append(word)
                    # Check if this word ends a sentence
                    if (word.endswith(('.', '!', '?')) or 
                        (i < len(words) - 1 and words[i + 1][0].isupper())):
                        sentences.append(' '.join(current))
                        current = []
                
                if current:  # Add any remaining words as a sentence
                    sentences.append(' '.join(current))
                
                # Process each sentence
                for sentence in sentences:
                    sentence_tokens = self._estimate_tokens(sentence)
                    
                    # If adding this sentence would exceed the optimal chunk size
                    if current_tokens + sentence_tokens > optimal_token_size and current_chunk:
                        chunks.append(' '.join(current_chunk))
                        current_chunk = [sentence]
                        current_tokens = sentence_tokens
                    else:
                        current_chunk.append(sentence)
                        current_tokens += sentence_tokens
            else:
                # If adding this paragraph would exceed the optimal chunk size
                if current_tokens + paragraph_tokens > optimal_token_size and current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = [paragraph]
                    current_tokens = paragraph_tokens
                else:
                    current_chunk.append(paragraph)
                    current_tokens += paragraph_tokens
        
        # Add the last chunk if there is one
        if current_chunk:
            chunks.append(' '.join(current_chunk))
        
        # Log chunk information
        logger.info(f"\nCreated {len(chunks)} chunks:")
        for i, chunk in enumerate(chunks, 1):
            chunk_tokens = self._estimate_tokens(chunk)
            logger.info(f"Chunk {i}: {len(chunk)} chars, {chunk_tokens} tokens")
        
        return chunks

    def _estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in a text using TikToken"""
        try:
            # Use the configured model's encoding
            encoding = encoding_for_model(self.llm_model)
            token_count = len(encoding.encode(text))
            logger.info(f"Estimated {token_count} tokens for text of length {len(text)}")
            return token_count
        except Exception as e:
            logger.warning(f"Error in token estimation using TikToken: {e}, using fallback")
            return len(text) // 4

    def _merge_summaries(self, summaries: List[Dict]) -> Dict:
        """Merge multiple chunk summaries into a single coherent summary"""
        merged = {
            "comprehensive_summary": "",
            "action_items": [],
            "key_insights": [],
            "wisdom": []
        }
        
        # Merge comprehensive summaries
        all_summaries = []
        for summary in summaries:
            if summary.get("comprehensive_summary"):
                all_summaries.append(summary["comprehensive_summary"])
        merged["comprehensive_summary"] = "\n\n".join(all_summaries)
        
        # Merge lists while removing duplicates
        for key in ["action_items", "key_insights", "wisdom"]:
            seen_items = set()
            for summary in summaries:
                for item in summary.get(key, []):
                    item_lower = item.lower()
                    if item_lower not in seen_items:
                        seen_items.add(item_lower)
                        merged[key].append(item)
        
        return merged

    def _detect_language_from_text(self, text: str) -> str:
        """Detect language using langdetect library"""
        try:
            # Detect language
            lang_code = detect(text)
            logger.info(f"Detected language: {lang_code}")
            return lang_code
        except Exception as e:
            logger.error(f"Error detecting language: {e}")
            return "en"  # Default to English if detection fails

    def _generate_structured_summary(self, transcript_text: str, target_language: str = "en") -> Dict:
        """Generate a structured summary with key insights and learnings in the specified language"""
        try:
            # Detect source language if not specified
            source_language = self._detect_language_from_text(transcript_text)
            logger.info(f"Source language: {source_language}, Target language: {target_language}")

            # Split text into manageable chunks - now using larger chunks for GPT-4
            chunks = self._chunk_text(transcript_text, max_chunk_size=100000)
            
            summaries = []
            for chunk_index, chunk in enumerate(chunks, 1):
                logger.info(f"Processing chunk {chunk_index}/{len(chunks)}")
                
                # Create system prompt with language instruction
                system_prompt = f"""You are a highly skilled AI that creates detailed summaries. 
                The user will provide a transcript chunk, and you should generate a structured summary in {target_language}.
                Focus on extracting key information and insights.
                
                Your response MUST be valid JSON with the following structure:
                {{
                    "comprehensive_summary": "A detailed summary of the main points and discussion",
                    "key_insights": ["List of key insights and takeaways"],
                    "action_items": ["List of actionable items or recommendations"],
                    "wisdom": ["List of wisdom, principles, or deeper learnings"],
                    "topics": ["List of main topics discussed"]
                }}
                
                Ensure your response is properly formatted JSON. All content must be in {target_language}."""

                # Create user prompt
                user_prompt = f"Please analyze and summarize the following transcript chunk (part {chunk_index}/{len(chunks)}):\n\n{chunk}"

                try:
                    # Generate summary using OpenAI
                    response = self.openai_client.chat.completions.create(
                        model=self.llm_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=self.llm_temperature,
                        max_tokens=4000,  # Consider using self.llm_max_tokens here
                        response_format={"type": "json_object"}
                    )

                    # Parse the response
                    summary_text = response.choices[0].message.content.strip()
                    logger.debug(f"Raw API response for chunk {chunk_index}: {summary_text[:500]}...")  # Log first 500 chars
                    
                    try:
                        summary_dict = json.loads(summary_text)
                        
                        # Validate required fields
                        required_fields = ["comprehensive_summary", "key_insights", "action_items", "wisdom", "topics"]
                        missing_fields = [field for field in required_fields if field not in summary_dict]
                        
                        if missing_fields:
                            logger.warning(f"Missing fields in summary: {missing_fields}")
                            # Initialize missing fields with empty values
                            for field in missing_fields:
                                summary_dict[field] = [] if field != "comprehensive_summary" else ""
                        
                        summaries.append(summary_dict)
                        logger.info(f"Successfully processed chunk {chunk_index}")
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parsing error in chunk {chunk_index}: {e}")
                        logger.error(f"Problematic response: {summary_text}")
                        # Create a minimal valid summary for this chunk
                        summaries.append({
                            "comprehensive_summary": f"Error processing chunk {chunk_index}",
                            "key_insights": [],
                            "action_items": [],
                            "wisdom": [],
                            "topics": []
                        })
                        
                except Exception as api_error:
                    logger.error(f"API error processing chunk {chunk_index}: {api_error}")
                    continue

            if not summaries:
                logger.error("No valid summaries generated")
                return {
                    "comprehensive_summary": "Error generating summary",
                    "key_insights": [],
                    "action_items": [],
                    "wisdom": [],
                    "topics": []
                }

            # Merge summaries from all chunks
            final_summary = self._merge_summaries(summaries)
            logger.info("Successfully generated and merged all summaries")
            return final_summary

        except Exception as e:
            logger.error(f"Error generating structured summary: {e}")
            traceback.print_exc()
            return {
                "comprehensive_summary": "Error generating summary",
                "key_insights": [],
                "action_items": [],
                "wisdom": [],
                "topics": []
            }

    def _process_chunk(self, chunk: str, chunk_num: int, total_chunks: int, lang_code: str) -> Optional[Dict]:
        """Process a single chunk of text and generate a summary"""
        prompt = f"""Analyze this podcast transcript section and provide a structured summary in {lang_code}:

1. Brief summary (1-2 paragraphs)
2. Key action items (bullet points)
3. Main insights (bullet points)
4. Core principles (bullet points)

Response must be in {lang_code} only.

Section {chunk_num}/{total_chunks}:
{chunk}

Format as JSON:
{{
    "comprehensive_summary": "summary text",
    "action_items": ["actions"],
    "key_insights": ["insights"],
    "wisdom": ["principles"]
}}"""

        try:
            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": "Create concise podcast summaries."},
                    {"role": "user", "content": prompt}
                ],
                temperature=self.llm_temperature,
                response_format={"type": "json_object"}
            )
            
            summary_text = response.choices[0].message.content
            return json.loads(summary_text)
        except Exception as e:
            print(f"Error processing chunk: {e}")
            return None

    def _generate_file_hash(self, url: str) -> str:
        """Generate a unique hash for a URL to use as filename"""
        return hashlib.sha256(url.encode()).hexdigest()[:12]
    
    def process_episode(self, url: str, title: Optional[str] = None) -> Dict:
        """Process a single podcast episode"""
        fetcher = PodcastFetcher()
        self._initialize_transcriber()
        
        try:
            # Generate file hash for storage
            file_hash = self._generate_file_hash(url)
            
            # First try to get metadata
            try:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,  # Only extract metadata
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    extracted_title = info.get("title")
                    if not extracted_title:
                        extracted_title = info.get("webpage_title")
                    
                    # Use the best available title
                    display_title = title or extracted_title or url
            except Exception as e:
                print(f"Warning: Could not extract metadata: {e}")
                display_title = title or url
            
            # Step 1: Download or get cached audio
            print(f"\n{'='*50}")
            print(f"Processing episode: {display_title}")
            print(f"{'='*50}")
            
            print("\n[Step 1/3] Audio Processing")
            print("-" * 20)
            audio_path = None
            
            # Check cache first
            cached_path = self.cache_manager.get_cached_download_path(url)
            if cached_path and cached_path.exists():
                print("✓ Using cached audio file")
                audio_path = cached_path
            else:
                print("⌛ Downloading audio...")
                audio_path = fetcher.download_episode(url, display_title)  # Pass the display_title to the fetcher
                if audio_path:
                    self.cache_manager.cache_download(url, audio_path)
                print("✓ Download complete")
            
            if not audio_path:
                raise RuntimeError("Failed to get audio file")
            
            # Step 2: Transcribe or get cached transcript
            print("\n[Step 2/3] Transcription")
            print("-" * 20)
            transcript = None
            transcript_path = None
            
            # Check transcript cache
            cached_transcript = self.cache_manager.get_cached_transcript_path(str(audio_path))
            if cached_transcript and cached_transcript.exists():
                print("✓ Using cached transcript")
                transcript_path = cached_transcript
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    transcript_text = f.read()
                transcript = {"text": transcript_text}
            else:
                print("⌛ Transcribing audio (this may take a while)...")
                transcript = self.transcriber.transcribe(audio_path)
                if transcript:
                    transcript_path = self.transcripts_dir / f"{file_hash}.txt"
                    with open(transcript_path, 'w', encoding='utf-8') as f:
                        f.write(transcript['text'])
                    self.cache_manager.cache_transcript(str(audio_path), transcript_path)
                    print("✓ Transcription complete")
            
            if not transcript:
                raise RuntimeError("Failed to get transcript")
            
            # Step 3: Generate structured summary
            print("\n[Step 3/3] Summarization")
            print("-" * 20)
            summary = None
            summary_path = None
            
            if self.settings.get("auto_summarize", True):
                # Generate cache path for summary
                summary_path = self.summaries_dir / f"{file_hash}_summary.json"
                
                if summary_path.exists():
                    print("✓ Using cached summary")
                    try:
                        with open(summary_path, 'r', encoding='utf-8') as f:
                            summary = json.load(f)
                    except json.JSONDecodeError:
                        print("Cached summary is corrupted, regenerating...")
                        summary = None
                
                if not summary:
                    print("⌛ Generating structured summary (this may take several minutes)...")
                    summary = self._generate_structured_summary(transcript['text'])
                    if summary:
                        # Ensure summary has content before saving
                        has_content = (
                            summary.get('comprehensive_summary') or 
                            summary.get('action_items') or 
                            summary.get('key_insights') or 
                            summary.get('wisdom')
                        )
                        if has_content:
                            with open(summary_path, 'w', encoding='utf-8') as f:
                                json.dump(summary, f, indent=2)
                            print("✓ Summary generation complete")
                        else:
                            print("⚠ Summary generation failed: Empty summary")
                            summary = None
                            summary_path = None
                    else:
                        print("⚠ Summary generation failed")
                
                # Validate summary structure
                if summary:
                    if not isinstance(summary.get('comprehensive_summary'), str):
                        summary['comprehensive_summary'] = ''
                    if not isinstance(summary.get('action_items'), list):
                        summary['action_items'] = []
                    if not isinstance(summary.get('key_insights'), list):
                        summary['key_insights'] = []
                    if not isinstance(summary.get('wisdom'), list):
                        summary['wisdom'] = []
            else:
                print("ℹ Summarization skipped (disabled in settings)")
            
            # Create result object
            print("\nFinalizing results...")
            processed_at = datetime.utcnow().isoformat()
            result = {
                "id": str(uuid.uuid4()),
                "url": url,
                "title": display_title,  # Use original title for display
                "file_hash": file_hash,  # Store file hash for reference
                "audio_path": str(audio_path),
                "transcript_path": str(transcript_path),
                "summary_path": str(summary_path) if summary_path else None,
                "processed_at": processed_at,
                "duration": transcript.get("duration", 0),
                "has_summary": bool(summary and summary_path),
                "summary": summary
            }
            
            # Save to history
            self._save_to_history(result)
            
            print("\n Processing complete!")
            print(f"{'='*50}\n")
            
            return result
            
        except Exception as e:
            print("\n⚠ Error during processing!")
            print(f"Error: {e}")
            raise RuntimeError(f"Failed to process episode: {e}")
    
    def get_history(self) -> List[Dict]:
        """Get processing history"""
        try:
            history_file = self._get_history_file()
            if not history_file.exists():
                return []
            
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            # Validate file paths and load summaries
            for entry in history:
                # Validate transcript path
                if 'transcript_path' in entry:
                    transcript_path = entry['transcript_path']
                    if transcript_path and Path(transcript_path).exists():
                        entry['transcript_path'] = str(transcript_path)
                    else:
                        entry['transcript_path'] = None
                
                # Validate summary path and load summary
                if 'summary_path' in entry:
                    summary_path = entry['summary_path']
                    if summary_path and Path(summary_path).exists():
                        try:
                            with open(summary_path, 'r', encoding='utf-8') as f:
                                entry['summary'] = json.load(f)
                                entry['has_summary'] = True
                        except Exception as e:
                            print(f"Error loading summary from {summary_path}: {e}")
                            entry['summary_path'] = None
                            entry['has_summary'] = False
                            entry['summary'] = None
                    else:
                        entry['summary_path'] = None
                        entry['has_summary'] = False
                        entry['summary'] = None
                
                # Add ID if missing (for backward compatibility)
                if 'id' not in entry:
                    entry['id'] = str(uuid.uuid4())
            
            return history
        except json.JSONDecodeError:
            print("Error decoding history file")
            return []
        except Exception as e:
            print(f"Error reading history: {e}")
            return []
    
    def _save_to_history(self, result: Dict):
        """Save processing result to history"""
        try:
            history_file = self._get_history_file()
            
            # Load existing history
            history = []
            if history_file.exists():
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except (json.JSONDecodeError, Exception) as e:
                    print(f"Error reading existing history: {e}")
            
            # Update existing entry or add new one
            existing_entry_index = next(
                (i for i, entry in enumerate(history) if entry['url'] == result['url']),
                None
            )
            
            if existing_entry_index is not None:
                # Update existing entry
                history[existing_entry_index].update(result)
            else:
                # Add new entry
                history.append(result)
            
            # Save updated history
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")
            raise RuntimeError(f"Failed to save processing history: {e}")

    def _get_voice_for_language(self, lang_code: str) -> tuple[str, str]:
        """Get the appropriate voice and speed for the detected language"""
        # OpenAI TTS voices have different characteristics:
        # - alloy: Most neutral, good for most languages
        # - echo: Clear and consistent
        # - fable: Expressive and dynamic
        # - nova: Natural and conversational
        # - onyx: Deep and authoritative
        # - shimmer: Warm and welcoming
        
        # Language groups and their optimal voice settings
        voice_settings = {
            # Germanic languages
            "en": ("nova", "1.0"),    # English
            "de": ("alloy", "0.9"),   # German
            "nl": ("alloy", "0.9"),   # Dutch
            "af": ("alloy", "0.9"),   # Afrikaans
            "da": ("alloy", "0.9"),   # Danish
            "no": ("alloy", "0.9"),   # Norwegian
            "sv": ("alloy", "0.9"),   # Swedish
            
            # Romance languages
            "es": ("alloy", "1.0"),   # Spanish
            "fr": ("alloy", "1.0"),   # French
            "it": ("alloy", "1.0"),   # Italian
            "pt": ("alloy", "1.0"),   # Portuguese
            "ro": ("alloy", "1.0"),   # Romanian
            "ca": ("alloy", "1.0"),   # Catalan
            
            # Slavic languages
            "ru": ("echo", "0.9"),    # Russian
            "uk": ("echo", "0.9"),    # Ukrainian
            "pl": ("echo", "0.9"),    # Polish
            "cs": ("echo", "0.9"),    # Czech
            "sk": ("echo", "0.9"),    # Slovak
            "bg": ("echo", "0.9"),    # Bulgarian
            "hr": ("echo", "0.9"),    # Croatian
            "sr": ("echo", "0.9"),    # Serbian
            
            # Asian languages
            "zh": ("fable", "0.8"),   # Chinese
            "ja": ("fable", "0.8"),   # Japanese
            "ko": ("fable", "0.8"),   # Korean
            "vi": ("fable", "0.9"),   # Vietnamese
            "th": ("fable", "0.9"),   # Thai
            "hi": ("fable", "0.9"),   # Hindi
            "bn": ("fable", "0.9"),   # Bengali
            "ta": ("fable", "0.9"),   # Tamil
            
            # Semitic languages
            "ar": ("onyx", "0.9"),    # Arabic
            "he": ("onyx", "0.9"),    # Hebrew
            
            # Turkic languages
            "tr": ("shimmer", "0.9"), # Turkish
            "az": ("shimmer", "0.9"), # Azerbaijani
            "uz": ("shimmer", "0.9"), # Uzbek
            
            # Other language families
            "fi": ("alloy", "0.9"),   # Finnish
            "hu": ("alloy", "0.9"),   # Hungarian
            "et": ("alloy", "0.9"),   # Estonian
            "el": ("alloy", "0.9"),   # Greek
            "id": ("alloy", "0.9"),   # Indonesian
            "ms": ("alloy", "0.9"),   # Malay
            "sw": ("alloy", "0.9"),   # Swahili
        }
        
        # Get voice settings or default to alloy with normal speed
        return voice_settings.get(lang_code, ("alloy", "1.0"))

    def generate_tts(self, text: str, filename: str) -> Optional[List[str]]:
        """Generate text-to-speech audio using OpenAI's API"""
        try:
            logger.info(f"Generating TTS for text of length {len(text)} with base filename {filename}")
            
            # Create TTS directory if it doesn't exist
            tts_dir = self.data_dir / "tts"
            tts_dir.mkdir(parents=True, exist_ok=True)
            
            # Detect language
            lang_code = self._detect_language_from_text(text)
            voice, speed = self._get_voice_for_language(lang_code)
            logger.info(f"Using voice '{voice}' with speed {speed} for language '{lang_code}'")
            
            # Calculate max chunk size for TTS
            # OpenAI TTS has a limit of 4096 tokens
            max_tts_tokens = 4096
            chars_per_token = 2 if lang_code in ['ar', 'he', 'fa'] else 4
            max_chunk_size = max_tts_tokens * chars_per_token
            
            # Generate unique filename
            file_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
            
            # If text is small enough, generate single file
            if len(text) <= max_chunk_size:
                output_path = tts_dir / f"{filename}_{file_hash}.mp3"
                
                # Check if audio already exists
                if output_path.exists():
                    return [str(output_path)]
                
                # Generate TTS using OpenAI
                response = self.openai_client.audio.speech.create(
                    model="tts-1",
                    voice=voice,
                    speed=float(speed),
                    input=text
                )
                
                # Save the audio file
                response.stream_to_file(str(output_path))
                return [str(output_path)]
            
            # For longer text, split into chunks
            text_chunks = self._chunk_text(text, max_chunk_size=max_chunk_size)
            logger.info(f"Split text into {len(text_chunks)} chunks")
            audio_paths = []
            
            for i, chunk in enumerate(text_chunks):
                # Generate unique filename for this chunk
                chunk_hash = hashlib.sha256(chunk.encode()).hexdigest()[:8]
                output_path = tts_dir / f"{filename}_{file_hash}_part{i}_{chunk_hash}.mp3"
                logger.debug(f"Processing chunk {i+1}/{len(text_chunks)}, output path: {output_path}")
                
                # Check if audio chunk already exists
                if output_path.exists():
                    logger.debug(f"Using cached audio file for chunk {i+1}")
                    audio_paths.append(str(output_path))
                    continue
                
                # Generate TTS using OpenAI
                logger.debug(f"Generating audio for chunk {i+1} (length: {len(chunk)})")
                response = self.openai_client.audio.speech.create(
                    model="tts-1",
                    voice=voice,
                    speed=float(speed),
                    input=chunk
                )
                
                # Save the audio file
                response.stream_to_file(str(output_path))
                logger.debug(f"Saved audio file for chunk {i+1}")
                audio_paths.append(str(output_path))
            
            logger.info(f"Successfully generated {len(audio_paths)} audio files")
            return audio_paths if audio_paths else None
            
        except Exception as e:
            logger.error(f"Error generating TTS: {e}")
            return None

    def get_summary_tts(self, episode_id: str) -> Optional[Dict[str, Union[str, List[str]]]]:
        """Get or generate TTS for each summary section"""
        try:
            logger.info(f"Getting summary TTS for episode: {episode_id}")
            
            # Get history
            history = self.get_history()
            
            # Find the episode
            episode = next((ep for ep in history if ep['id'] == episode_id), None)
            if not episode or not episode.get('summary'):
                logger.warning(f"No episode or summary found for ID: {episode_id}")
                return None
            
            summary = episode['summary']
            logger.debug(f"Found episode summary for ID: {episode_id}")
            
            tts_paths = {}
            
            # Generate TTS for comprehensive summary
            if summary.get('comprehensive_summary'):
                logger.debug("Generating TTS for comprehensive summary")
                tts_paths['comprehensive_summary'] = self.generate_tts(
                    summary['comprehensive_summary'],
                    f"{episode_id}_summary"
                )
            
            # Generate TTS for action items
            if summary.get('action_items'):
                logger.debug("Generating TTS for action items")
                text = "Action Items:\n" + "\n".join(f"- {item}" for item in summary['action_items'])
                tts_paths['action_items'] = self.generate_tts(
                    text,
                    f"{episode_id}_actions"
                )
            
            # Generate TTS for key insights
            if summary.get('key_insights'):
                logger.debug("Generating TTS for key insights")
                text = "Key Insights:\n" + "\n".join(f"- {item}" for item in summary['key_insights'])
                tts_paths['key_insights'] = self.generate_tts(
                    text,
                    f"{episode_id}_insights"
                )
            
            # Generate TTS for wisdom
            if summary.get('wisdom'):
                logger.debug("Generating TTS for wisdom")
                text = "Wisdom and Principles:\n" + "\n".join(f"- {item}" for item in summary['wisdom'])
                tts_paths['wisdom'] = self.generate_tts(
                    text,
                    f"{episode_id}_wisdom"
                )
            
            logger.info(f"Generated TTS for {len(tts_paths)} sections")
            return tts_paths
            
        except Exception as e:
            logger.error(f"Error getting summary TTS: {e}", exc_info=True)
            return None

    def refresh_episode_metadata(self, url: str) -> Dict:
        """Refresh metadata for an episode without redownloading"""
        try:
            # Extract metadata without downloading
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,  # Only extract metadata
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                extracted_title = info.get("title")
                if not extracted_title:
                    extracted_title = info.get("webpage_title")
                
                metadata = {
                    "title": extracted_title,
                    "description": info.get("description"),
                    "webpage_url": info.get("webpage_url"),
                    "uploader": info.get("uploader"),
                }
                
                # Update history
                history_file = self._get_history_file()
                if history_file.exists():
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                    
                    # Find and update the episode
                    for entry in history:
                        if entry['url'] == url:
                            entry['title'] = metadata['title']
                            entry['description'] = metadata.get('description')
                            entry['webpage_url'] = metadata.get('webpage_url')
                            entry['uploader'] = metadata.get('uploader')
                            break
                    
                    # Save updated history
                    with open(history_file, 'w', encoding='utf-8') as f:
                        json.dump(history, f, indent=2)
                
                return metadata
                
        except Exception as e:
            print(f"Error refreshing metadata: {e}")
            raise RuntimeError(f"Failed to refresh metadata: {e}")

    def search_podcasts(self, query: str) -> List[Dict]:
        """Search for podcasts using iTunes API"""
        print(f"Service: Searching for podcasts with query: {query}")
        base_url = "https://itunes.apple.com/search"
        params = {
            "term": query,
            "media": "podcast",
            "limit": 10
        }
        
        try:
            response = requests.get(base_url, params=params)
            print(f"Service: Response status code: {response.status_code}")
            if response.status_code == 200:
                results = response.json().get('results', [])
                print(f"Service: Found {len(results)} results")
                return [
                    {
                        'id': str(podcast.get('collectionId')),
                        'title': podcast.get('trackName', ''),
                        'author': podcast.get('artistName', ''),
                        'feed_url': podcast.get('feedUrl', ''),
                        'artwork': podcast.get('artworkUrl600', ''),
                        'description': podcast.get('collectionCensoredName', ''),
                        'itunes_url': podcast.get('collectionViewUrl', '')
                    }
                    for podcast in results
                    if podcast.get('feedUrl')
                ]
            print(f"Service: API request failed with status {response.status_code}")
            return []
        except Exception as e:
            print(f"Service: Error searching podcasts: {e}")
            return []

    def subscribe_to_podcast(self, podcast_id: str, feed_url: str, title: str = '') -> bool:
        """Subscribe to a podcast feed"""
        try:
            subscription = {
                'id': podcast_id,
                'feed_url': feed_url,
                'title': title,
                'type': 'podcast'
            }
            self.cache_manager.save_subscription(subscription)
            return True
        except Exception as e:
            print(f"Error subscribing to podcast: {e}")
            return False

    def subscribe_to_youtube(self, channel_url: str) -> bool:
        """Subscribe to a YouTube channel"""
        try:
            print(f"\n{'='*50}")
            print(f"Subscribing to YouTube channel: {channel_url}")
            print(f"{'='*50}\n")
            
            # Extract channel ID from URL
            print("Step 1: Extracting channel ID...")
            channel_id = self._extract_youtube_channel_id(channel_url)
            if not channel_id:
                raise ValueError("Could not extract channel ID from URL")
            print(f"✓ Extracted channel ID: {channel_id}")
            
            # Use yt-dlp to get channel info
            print("\nStep 2: Fetching channel info...")
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,  # Only fetch metadata
                'no_download': True,   # Don't download anything
                'skip_download': True  # Skip download
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://youtube.com/channel/{channel_id}", download=False)
                channel_title = info.get('channel', '') or info.get('uploader', '')
            print(f"✓ Got channel title: {channel_title}")
            
            print("\nStep 3: Saving subscription...")
            subscription = {
                'id': channel_id,
                'url': channel_url,
                'title': channel_title,
                'type': 'youtube'
            }
            print(f"Subscription data: {json.dumps(subscription, indent=2)}")
            
            self.cache_manager.save_subscription(subscription)
            print("✓ Subscription saved successfully")
            return True
        except Exception as e:
            print(f"\n⚠ Error subscribing to YouTube channel:")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"Stack trace:")
            traceback.print_exc()
            return False

    def _extract_youtube_channel_id(self, url: str) -> Optional[str]:
        """Extract YouTube channel ID from URL"""
        try:
            print(f"\nExtracting channel ID from URL: {url}")
            # Handle different YouTube URL formats
            if 'youtube.com/channel/' in url:
                print("Detected direct channel URL format")
                channel_id = url.split('youtube.com/channel/')[-1].split('/')[0]
                print(f"Extracted channel ID: {channel_id}")
                return channel_id
            
            # For all other formats, use yt-dlp
            print("Using yt-dlp to extract channel info...")
            with yt_dlp.YoutubeDL({
                'quiet': False,
                'verbose': True,
                'extract_flat': True,
                'no_warnings': False
            }) as ydl:
                print("Extracting info from URL...")
                info = ydl.extract_info(url, download=False)
                print("Got channel info from yt-dlp")
                
                channel_id = info.get('channel_id')
                if not channel_id:
                    print("No channel ID found in yt-dlp response")
                    raise ValueError("Could not extract channel ID")
                
                print(f"Successfully extracted channel ID: {channel_id}")
                return channel_id
        except Exception as e:
            print(f"\n⚠ Error extracting YouTube channel ID:")
            print(f"Error type: {type(e).__name__}")
            print(f"Error message: {str(e)}")
            print(f"Stack trace:")
            traceback.print_exc()
            return None

    def refresh_episodes(self) -> Dict:
        """Refresh episodes for all subscriptions"""
        print("Refreshing episodes...")
        try:
            subscriptions = self.cache_manager.get_all_subscriptions()
            new_episodes = {'podcast': {}, 'youtube': {}}
            
            for sub in subscriptions:
                print(f"Processing subscription: {sub}")
                if sub['type'] == 'podcast':
                    print(f"Fetching episodes from feed: {sub['feed_url']}")
                    try:
                        episodes = self.podcast_fetcher.fetch_episodes(sub['feed_url'])
                        # Add subscription info to episodes
                        for episode in episodes:
                            if not episode.get('id'):
                                episode['id'] = hashlib.sha256(
                                    f"{sub['id']}_{episode.get('title')}_{episode.get('published')}".encode()
                                ).hexdigest()[:12]
                            episode['subscription_id'] = sub['id']
                            episode['subscription_type'] = 'podcast'
                            new_episodes['podcast'][episode['id']] = episode
                    except Exception as e:
                        print(f"Error fetching episodes for subscription {sub['id']}: {e}")
                        continue
                elif sub['type'] == 'youtube':
                    print(f"Fetching videos from channel: {sub['url']}")
                    try:
                        ydl_opts = {
                            'quiet': True,
                            'extract_flat': True,
                            'no_download': True,
                            'skip_download': True,
                            'playlistend': 30  # Increased to get more videos for categorization
                        }
                        
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            channel_info = ydl.extract_info(
                                f"https://youtube.com/channel/{sub['id']}/videos",
                                download=False
                            )
                            
                            if channel_info and 'entries' in channel_info:
                                for video in channel_info['entries']:
                                    if video:
                                        video_id = video.get('id')
                                        if video_id:
                                            # Determine content type
                                            is_short = video.get('duration', 0) <= 60  # Shorts are typically ≤ 60 seconds
                                            is_stream = video.get('was_live', False) or 'stream' in video.get('title', '').lower()
                                            
                                            episode = {
                                                'id': video_id,
                                                'title': video.get('title', ''),
                                                'description': video.get('description', ''),
                                                'published': video.get('upload_date', ''),
                                                'audio_url': f"https://youtube.com/watch?v={video_id}",
                                                'duration': video.get('duration', ''),
                                                'image': video.get('thumbnail', ''),
                                                'link': f"https://youtube.com/watch?v={video_id}",
                                                'subscription_id': sub['id'],
                                                'subscription_type': 'youtube',
                                                'is_short': is_short,
                                                'is_stream': is_stream,
                                                'processed': False
                                            }
                                            new_episodes['youtube'][video_id] = episode
                    except Exception as e:
                        print(f"Error fetching videos for channel {sub['id']}: {e}")
                        continue
            
            # Save episodes to cache
            try:
                self.cache_manager.save_episodes(new_episodes)
            except Exception as e:
                print(f"Error saving episodes to cache: {e}")
            
            print(f"Found {len(new_episodes['podcast'])} podcast episodes and {len(new_episodes['youtube'])} YouTube videos")
            return new_episodes
        except Exception as e:
            print(f"Error refreshing episodes: {e}")
            return {'podcast': {}, 'youtube': {}}