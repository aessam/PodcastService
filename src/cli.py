#!/usr/bin/env python3
import argparse
from pathlib import Path
import os
import sys
import json
from typing import Optional, List
from getpass import getpass

# Add the parent directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from podcast_service.src.core.service import PodcastService
from podcast_service.config.settings import DATA_DIR

def register_user(service: PodcastService):
    """Register a new user"""
    print("\n=== User Registration ===")
    username = input("Username: ").strip()
    email = input("Email: ").strip()
    password = getpass("Password: ")
    confirm_password = getpass("Confirm password: ")
    
    if password != confirm_password:
        print("Passwords do not match!")
        return False
    
    try:
        user = service.register_user(username, email, password)
        print(f"\nSuccessfully registered user: {user.username}")
        return True
    except ValueError as e:
        print(f"\nRegistration failed: {e}")
        return False

def login(service: PodcastService) -> bool:
    """Log in a user"""
    print("\n=== User Login ===")
    username = input("Username: ").strip()
    password = getpass("Password: ")
    
    if service.login(username, password):
        print(f"\nWelcome back, {username}!")
        return True
    else:
        print("\nInvalid username or password")
        return False

def show_settings(service: PodcastService):
    """Show current user settings"""
    settings = service.get_user_settings()
    if settings:
        print("\n=== Current Settings ===")
        for key, value in settings.items():
            print(f"{key}: {value}")
    else:
        print("\nNo user logged in")

def update_settings(service: PodcastService):
    """Update user settings"""
    settings = service.get_user_settings()
    if not settings:
        print("\nNo user logged in")
        return
    
    print("\n=== Update Settings ===")
    print("Current settings:")
    for key, value in settings.items():
        print(f"{key}: {value}")
    
    print("\nEnter new values (press Enter to keep current value):")
    new_settings = {}
    
    model = input(f"Default model [{settings['default_model']}]: ").strip()
    if model:
        new_settings['default_model'] = model
    
    format = input(f"Output format [{settings['output_format']}]: ").strip()
    if format:
        new_settings['output_format'] = format
    
    auto_sum = input(f"Auto-summarize [{settings['auto_summarize']}] (true/false): ").strip().lower()
    if auto_sum in ('true', 'false'):
        new_settings['auto_summarize'] = auto_sum == 'true'
    
    if new_settings:
        if service.update_user_settings(new_settings):
            print("\nSettings updated successfully")
        else:
            print("\nFailed to update settings")
    else:
        print("\nNo changes made")

def show_history(service: PodcastService):
    """Show processing history"""
    history = service.get_user_history()
    if not history:
        print("\nNo processing history found")
        return
    
    print("\n=== Processing History ===")
    for entry in history:
        print(f"\nTitle: {entry['title']}")
        print(f"URL: {entry['url']}")
        print(f"Processed: {entry['processed_at']}")
        print(f"Duration: {entry['duration']:.2f} seconds")
        print(f"Has summary: {entry['has_summary']}")

def process_episode(service: PodcastService, url: str, title: Optional[str] = None):
    """Process a single episode"""
    try:
        result = service.process_episode(url, title)
        print("\nProcessing completed successfully!")
        print(f"Title: {result['title']}")
        print(f"Audio saved to: {result['audio_path']}")
        print(f"Transcript saved to: {result['transcript_path']}")
        print(f"Duration: {result['duration']:.2f} seconds")
        if result['has_summary']:
            print("Summary generated successfully")
    except Exception as e:
        print(f"\nError processing episode: {e}")

def load_feed_list(file_path: Path) -> List[str]:
    """Load podcast feed URLs from a JSON file"""
    if not file_path.exists():
        return []
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            return data.get('feeds', [])
    except Exception:
        return []

def save_feed_list(file_path: Path, feeds: List[str]):
    """Save podcast feed URLs to a JSON file"""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump({'feeds': feeds}, f, indent=2)

def manage_feeds(service: PodcastService, args):
    """Manage podcast feeds for the current user"""
    if not service.current_user:
        print("\nPlease log in first")
        return

    user_feeds_file = service.data_dir / service.current_user.user_id / "podcast_feeds.json"
    feeds = load_feed_list(user_feeds_file)

    if args.command == 'add-feed':
        feeds.extend(args.urls)
        feeds = list(set(feeds))  # Remove duplicates
        save_feed_list(user_feeds_file, feeds)
        print(f"\nAdded {len(args.urls)} feed(s). Total feeds: {len(feeds)}")

    elif args.command == 'list-feeds':
        if not feeds:
            print("\nNo feeds configured")
            return
        print("\nConfigured podcast feeds:")
        for i, feed in enumerate(feeds, 1):
            print(f"{i}. {feed}")

    elif args.command == 'remove-feed':
        original_count = len(feeds)
        feeds = [f for f in feeds if f not in args.urls]
        save_feed_list(user_feeds_file, feeds)
        print(f"\nRemoved {original_count - len(feeds)} feed(s). Remaining feeds: {len(feeds)}")

def process_feeds(service: PodcastService, force: bool = False):
    """Process all podcast feeds for the current user"""
    if not service.current_user:
        print("\nPlease log in first")
        return

    user_feeds_file = service.data_dir / service.current_user.user_id / "podcast_feeds.json"
    feeds = load_feed_list(user_feeds_file)

    if not feeds:
        print("\nNo feeds configured. Add feeds using the 'add-feed' command.")
        return

    try:
        results = service.process_feeds(feeds, force)
        print(f"\nProcessed {len(results)} new episodes")
        for result in results:
            print(f"\nTitle: {result['title']}")
            print(f"Duration: {result['duration']:.2f} seconds")
            if result['has_summary']:
                print("Summary generated")
    except Exception as e:
        print(f"\nError processing feeds: {e}")

def main():
    parser = argparse.ArgumentParser(description="Podcast Service CLI")
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # User management commands
    subparsers.add_parser('register', help='Register a new user')
    subparsers.add_parser('login', help='Log in')
    subparsers.add_parser('logout', help='Log out')
    
    # Settings commands
    settings_parser = subparsers.add_parser('settings', help='Manage settings')
    settings_subparsers = settings_parser.add_subparsers(dest='settings_command')
    settings_subparsers.add_parser('show', help='Show current settings')
    settings_subparsers.add_parser('update', help='Update settings')
    
    # History command
    subparsers.add_parser('history', help='Show processing history')
    
    # Feed management commands
    add_feed = subparsers.add_parser('add-feed', help='Add podcast feed URLs')
    add_feed.add_argument('urls', nargs='+', help='One or more podcast feed URLs')
    
    subparsers.add_parser('list-feeds', help='List all podcast feed URLs')
    
    remove_feed = subparsers.add_parser('remove-feed', help='Remove podcast feed URLs')
    remove_feed.add_argument('urls', nargs='+', help='One or more podcast feed URLs to remove')
    
    # Process commands
    process_parser = subparsers.add_parser('process', help='Process podcast feeds or single episode')
    process_subparsers = process_parser.add_subparsers(dest='process_command')
    
    # Process feeds command
    feeds_parser = process_subparsers.add_parser('feeds', help='Process all podcast feeds')
    feeds_parser.add_argument('--force', action='store_true', help='Process all episodes, including previously processed ones')
    
    # Process single episode command
    episode_parser = process_subparsers.add_parser('episode', help='Process a single episode')
    episode_parser.add_argument('url', help='URL of the podcast episode')
    episode_parser.add_argument('--title', help='Optional title for the episode')
    
    args = parser.parse_args()
    
    # Initialize service
    service = PodcastService(Path(DATA_DIR))
    
    if args.command == 'register':
        register_user(service)
    
    elif args.command == 'login':
        login(service)
    
    elif args.command == 'logout':
        service.logout()
        print("\nLogged out successfully")
    
    elif args.command == 'settings':
        if args.settings_command == 'show':
            show_settings(service)
        elif args.settings_command == 'update':
            update_settings(service)
        else:
            settings_parser.print_help()
    
    elif args.command == 'history':
        show_history(service)
    
    elif args.command in ('add-feed', 'list-feeds', 'remove-feed'):
        manage_feeds(service, args)
    
    elif args.command == 'process':
        if not service.current_user:
            print("\nPlease log in first")
            sys.exit(1)
            
        if args.process_command == 'feeds':
            process_feeds(service, args.force)
        elif args.process_command == 'episode':
            process_episode(service, args.url, args.title)
        else:
            process_parser.print_help()
    
    else:
        parser.print_help()

if __name__ == '__main__':
    main() 