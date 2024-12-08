from pathlib import Path
from typing import Optional, Dict, List, Union
import os
from datetime import datetime
import json
import uuid
import hashlib
import logging

from podcast_service.src.core.transcriber import Transcriber
from podcast_service.src.core.podcast_fetcher import PodcastFetcher
from podcast_service.src.summarization.summarizer import Summarizer
from podcast_service.src.utils.cache_manager import CacheManager
from openai import OpenAI
import io

logger = logging.getLogger(__name__)

class PodcastService:
    def __init__(self, data_dir: Path = Path("data")):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Initialized PodcastService with data directory: {data_dir}")
        
        # Initialize OpenAI client
        self.openai_client = OpenAI()
        
        # Initialize cache manager
        self.cache_manager = CacheManager(self.data_dir / "cache")
        
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
    
    def _chunk_text(self, text: str, max_length: int = 4000) -> List[str]:
        """Split text into chunks that fit within max length while respecting sentence boundaries."""
        # Split into sentences
        sentences = [s.strip() for s in text.replace('\n', ' ').split('.') if s.strip()]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            # Add period back and account for it in length
            sentence = sentence + '.'
            sentence_length = len(sentence)
            
            if current_length + sentence_length > max_length:
                if current_chunk:  # Save current chunk if it exists
                    chunks.append(' '.join(current_chunk))
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                current_chunk.append(sentence)
                current_length += sentence_length
        
        if current_chunk:  # Add the last chunk
            chunks.append(' '.join(current_chunk))
        
        return chunks

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

    def _generate_structured_summary(self, transcript_text: str) -> Dict:
        """Generate a structured summary with key insights and learnings"""
        try:
            # Split transcript into chunks
            chunks = self._chunk_text(transcript_text)
            chunk_summaries = []
            
            # Process each chunk
            for i, chunk in enumerate(chunks, 1):
                print(f"Processing chunk {i} of {len(chunks)}...")
                
                prompt = f"""Please analyze the following section of a podcast transcript and provide a structured summary with these specific sections:

1. COMPREHENSIVE SUMMARY
Provide a detailed yet concise summary of the main discussion points and key ideas in this section (1-2 paragraphs).

2. ACTION ITEMS
List specific actions, recommendations, or practical steps mentioned that listeners could implement. Format as a bullet-point list.

3. KEY INSIGHTS & NUANCES
Identify subtle but important points, nuanced perspectives, or interesting angles discussed. Format as a bullet-point list.

4. WISDOM & PRINCIPLES
Extract timeless wisdom, mental models, principles, or philosophical insights shared. Format as a bullet-point list.

Transcript Section {i}/{len(chunks)}:
{chunk}

Format your response as a JSON object with these exact keys:
{{
    "comprehensive_summary": "string with the summary",
    "action_items": ["array", "of", "action items"],
    "key_insights": ["array", "of", "insights"],
    "wisdom": ["array", "of", "wisdom points"]
}}"""

                try:
                    response = self.openai_client.chat.completions.create(
                        model="gpt-4",
                        messages=[
                            {"role": "system", "content": "You are an expert at analyzing podcast content and extracting valuable insights. Focus on providing actionable insights and clear, structured summaries. Always return a valid JSON object with the specified structure."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.7,
                        max_tokens=2000
                    )

                    # Parse the response into a structured format
                    summary_text = response.choices[0].message.content.strip()
                    
                    # Ensure we have valid JSON
                    try:
                        summary_dict = json.loads(summary_text)
                    except json.JSONDecodeError as e:
                        print(f"Error parsing JSON from chunk {i}, attempting to fix: {e}")
                        # Try to extract JSON from the text
                        json_start = summary_text.find('{')
                        json_end = summary_text.rfind('}') + 1
                        if json_start >= 0 and json_end > json_start:
                            try:
                                summary_dict = json.loads(summary_text[json_start:json_end])
                            except json.JSONDecodeError:
                                print(f"Failed to extract JSON from chunk {i}")
                                continue
                        else:
                            print(f"No JSON found in chunk {i}")
                            continue

                    # Validate and fix structure
                    valid_summary = {
                        "comprehensive_summary": "",
                        "action_items": [],
                        "key_insights": [],
                        "wisdom": []
                    }

                    # Copy over values, ensuring correct types
                    if isinstance(summary_dict.get("comprehensive_summary"), str):
                        valid_summary["comprehensive_summary"] = summary_dict["comprehensive_summary"].strip()
                    
                    for key in ["action_items", "key_insights", "wisdom"]:
                        if isinstance(summary_dict.get(key), list):
                            valid_summary[key] = [str(item).strip() for item in summary_dict[key] if item]
                        elif isinstance(summary_dict.get(key), str) and summary_dict[key].strip():
                            # If it's a non-empty string, try to split it into a list
                            valid_summary[key] = [item.strip() for item in summary_dict[key].split('\n') if item.strip()]

                    # Only add if there's actual content
                    if (valid_summary["comprehensive_summary"] or 
                        valid_summary["action_items"] or 
                        valid_summary["key_insights"] or 
                        valid_summary["wisdom"]):
                        chunk_summaries.append(valid_summary)

                except Exception as e:
                    print(f"Error processing chunk {i}: {e}")
                    continue

            # Merge all chunk summaries
            if chunk_summaries:
                merged = self._merge_summaries(chunk_summaries)
                # Verify the merged summary has content
                if (merged['comprehensive_summary'] or 
                    merged['action_items'] or 
                    merged['key_insights'] or 
                    merged['wisdom']):
                    return merged
            
            raise Exception("No valid summary content generated from any chunk")

        except Exception as e:
            print(f"Error generating structured summary: {e}")
            # Return empty but valid structure
            return {
                "comprehensive_summary": "",
                "action_items": [],
                "key_insights": [],
                "wisdom": []
            }
    
    def _generate_file_hash(self, url: str) -> str:
        """Generate a unique hash for a URL to use as filename"""
        return hashlib.sha256(url.encode()).hexdigest()[:12]
    
    def process_episode(self, url: str, title: Optional[str] = None) -> Dict:
        """Process a single podcast episode"""
        # Initialize components
        fetcher = PodcastFetcher(self.downloads_dir, cache_manager=self.cache_manager)
        self._initialize_transcriber()
        
        try:
            # Generate file hash for storage
            file_hash = self._generate_file_hash(url)
            display_title = title or url  # Keep original title for display
            
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
                audio_path = fetcher.download_episode(url, file_hash)
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
            
            print("\n✓ Processing complete!")
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
            
            # Add new result to history
            history.append(result)
            
            # Save updated history
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
        except Exception as e:
            print(f"Error saving history: {e}")
            raise RuntimeError(f"Failed to save processing history: {e}")

    def generate_tts(self, text: str, filename: str) -> Optional[List[str]]:
        """Generate text-to-speech audio using OpenAI's API, returns list of audio file paths"""
        try:
            logger.info(f"Generating TTS for text of length {len(text)} with base filename {filename}")
            
            # Create TTS directory if it doesn't exist
            tts_dir = self.data_dir / "tts"
            tts_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate base filename
            file_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
            base_path = tts_dir / f"{filename}_{file_hash}"
            logger.debug(f"Base path for audio files: {base_path}")
            
            # Split text into chunks
            text_chunks = self._chunk_text(text)
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
                    voice="nova",
                    input=chunk
                )
                
                # Save the audio file
                response.stream_to_file(str(output_path))
                logger.debug(f"Saved audio file for chunk {i+1}")
                audio_paths.append(str(output_path))
            
            logger.info(f"Successfully generated {len(audio_paths)} audio files")
            return audio_paths if audio_paths else None
            
        except Exception as e:
            logger.error(f"Error generating TTS: {e}", exc_info=True)
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