#!/usr/bin/env python3
import os
from pathlib import Path
import shutil

AVAILABLE_MODELS = {
    'tiny': 'mlx-community/whisper-tiny-mlx',
    'base': 'mlx-community/whisper-base-mlx',
    'small': 'mlx-community/whisper-small-mlx',
    'medium': 'mlx-community/whisper-medium-mlx',
    'large': 'mlx-community/whisper-large-mlx',
    'large-v2': 'mlx-community/whisper-large-v2-mlx',
    'large-v3': 'mlx-community/whisper-large-v3-mlx'
}

def validate_whisper_path(path: str) -> bool:
    """
    Validate that the given path contains a valid MLX Whisper model.
    Checks for the presence of required model files.
    """
    # If it's a model name or hub path, accept it
    if path.lower() in AVAILABLE_MODELS or '/' in path:
        return True

    # Otherwise, check for local model files
    model_path = Path(path)
    required_files = ['config.json', 'model.safetensors', 'tokenizer.json']
    
    if not model_path.exists():
        print(f"Error: Path does not exist: {path}")
        return False
    
    if not model_path.is_dir():
        print(f"Error: Path is not a directory: {path}")
        return False
    
    missing_files = [f for f in required_files if not (model_path / f).exists()]
    if missing_files:
        print(f"Error: Missing required model files: {', '.join(missing_files)}")
        return False
    
    return True

def show_available_models():
    """Show available MLX Whisper models."""
    print("\nAvailable MLX Whisper models:")
    for name, path in AVAILABLE_MODELS.items():
        print(f"- {name}: {path}")
    print("\nYou can either:")
    print("1. Enter one of the model names above (e.g., 'large-v3')")
    print("2. Provide a path to a local model directory")
    print("3. Provide a custom MLX Hub model path")

def setup_environment():
    """Set up the environment variables for the podcast service."""
    # Get the project root directory
    project_root = Path(__file__).resolve().parent.parent
    
    # Check if .env already exists
    env_file = project_root / '.env'
    if env_file.exists():
        print("\nWarning: .env file already exists!")
        overwrite = input("Do you want to overwrite it? (y/N): ").lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return
    
    # Copy template to .env
    template_file = project_root / '.env.template'
    if not template_file.exists():
        print("Error: .env.template file not found!")
        return
    
    # Get user input for environment variables
    print("\nPlease provide the following information:")
    
    openai_key = input("\nOpenAI API Key: ").strip()
    while not openai_key:
        print("Error: OpenAI API Key is required!")
        openai_key = input("OpenAI API Key: ").strip()
    
    # Show available models before asking for path
    show_available_models()
    
    while True:
        whisper_path = input("\nMLX Whisper Model (name or path): ").strip()
        if not whisper_path:
            print("Error: MLX Whisper Model is required!")
            continue
        
        # If it's a local path, resolve it
        if os.path.exists(whisper_path):
            whisper_path = str(Path(whisper_path).expanduser().resolve())
        
        if validate_whisper_path(whisper_path):
            if whisper_path.lower() in AVAILABLE_MODELS:
                print(f"Will use model from MLX Hub: {AVAILABLE_MODELS[whisper_path.lower()]}")
            elif '/' in whisper_path:
                print(f"Will use custom model from MLX Hub: {whisper_path}")
            else:
                print("Local model path validated successfully!")
            break
        else:
            print("\nInvalid model specification. Please try again.")
            show_available_models()
    
    # Optional settings
    print("\nOptional Settings (press Enter to use defaults):")
    llm_model = input("LLM Model (default: gpt-4): ").strip() or "gpt-4"
    llm_tokens = input("Max Tokens (default: 4096): ").strip() or "4096"
    llm_temp = input("Temperature (default: 0.8): ").strip() or "0.8"
    
    # Create .env file with user input
    env_content = f"""# OpenAI API Key
OPENAI_API_KEY={openai_key}

# MLX Whisper Model Path
WHISPER_MODEL_PATH={whisper_path}

# LLM Settings
LLM_MODEL={llm_model}
LLM_MAX_TOKENS={llm_tokens}
LLM_TEMPERATURE={llm_temp}
"""
    
    # Write the .env file
    with open(env_file, 'w') as f:
        f.write(env_content)
    
    print("\nEnvironment setup complete!")
    print(f"Configuration saved to: {env_file}")
    print("\nNote: Make sure to keep your .env file secure and never commit it to version control.")

if __name__ == '__main__':
    setup_environment() 