from pathlib import Path
from typing import Optional
import json
from datetime import datetime
import time
import openai
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from podcast_service.src.summarization.templates import PODCAST_SUMMARY_TEMPLATE

class Summarizer:
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = Path(output_dir) if output_dir else Path("summaries")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        print("Initializing summarizer...")
        
        # Initialize OpenAI client
        self.llm = ChatOpenAI(
            model_name="gpt-4",
            temperature=0.5
        )
        
        # Configure text splitter for initial chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=8000,  # Reduced chunk size
            chunk_overlap=800,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # Create the summary chains
        self.map_prompt = PromptTemplate(
            template="Summarize this section of the podcast transcript, focusing on key points and insights:\n\n{text}",
            input_variables=["text"]
        )
        
        self.combine_prompt = PromptTemplate(
            template=PODCAST_SUMMARY_TEMPLATE,
            input_variables=["text"]
        )
        
        self.chain = load_summarize_chain(
            llm=self.llm,
            chain_type="map_reduce",
            map_prompt=self.map_prompt,
            combine_prompt=self.combine_prompt,
            verbose=True
        )
        
        print("Summarizer initialized successfully")

    def _log_progress(self, message: str, start_time: float = None):
        """Log progress with timestamp and elapsed time"""
        now = datetime.now().strftime("%H:%M:%S")
        if start_time:
            elapsed = time.time() - start_time
            print(f"[{now}] {message} (Elapsed: {elapsed:.1f}s)")
        else:
            print(f"[{now}] {message}")

    def generate_summary(self, text: str) -> Optional[str]:
        """Generate a summary of the transcript"""
        try:
            start_time = time.time()
            self._log_progress("Starting summary generation...")
            
            # Split text into chunks
            self._log_progress("Splitting transcript into chunks...")
            chunks = self.text_splitter.split_text(text)
            
            # Convert chunks to documents
            docs = [Document(page_content=chunk) for chunk in chunks]
            
            self._log_progress(f"Processing transcript in {len(chunks)} chunks...")
            
            # Process each chunk
            for i, chunk in enumerate(chunks, 1):
                chunk_start = time.time()
                self._log_progress(f"Processing chunk {i}/{len(chunks)}...")
                
                # The actual processing happens in the chain
                # Just log the start of each chunk
                self._log_progress(f"Sending chunk {i} to OpenAI (size: {len(chunk)} chars)...")
            
            # Generate final summary
            self._log_progress("Generating final summary from all chunks...")
            summary = self.chain.invoke({"input_documents": docs})
            
            self._log_progress("Summary generation complete!", start_time)
            
            return summary['output_text']
            
        except Exception as e:
            self._log_progress(f"Error generating summary: {e}")
            return None

    def save_summary(self, summary: str, filename: str):
        """Save the summary to a file"""
        if not summary:
            return
        
        start_time = time.time()
        self._log_progress("Saving summary to file...")
            
        try:
            # Create summary object
            summary_data = {
                "summary": summary,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Ensure filename is safe and create full path
            safe_filename = Path(filename).stem  # Get just the filename without path or extension
            summary_path = self.output_dir / f"{safe_filename}.json"
            
            # Ensure output directory exists
            self.output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save to file
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary_data, f, indent=2)
            
            self._log_progress(f"Summary saved to {summary_path}", start_time)
            return str(summary_path)
        except Exception as e:
            self._log_progress(f"Error saving summary: {e}")
            return None 