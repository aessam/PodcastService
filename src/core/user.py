from pathlib import Path
import json
import os
from typing import Dict, Optional
from datetime import datetime
import hashlib
import uuid

class User:
    def __init__(self, username: str, email: str, user_id: Optional[str] = None, created_at: Optional[str] = None):
        self.username = username
        self.email = email
        self.user_id = user_id or str(uuid.uuid4())
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.settings = {
            "default_model": "base",
            "output_format": "txt",
            "auto_summarize": True
        }

    def to_dict(self) -> Dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at,
            "settings": self.settings
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'User':
        user = cls(
            username=data["username"],
            email=data["email"],
            user_id=data["user_id"],
            created_at=data["created_at"]
        )
        user.settings = data["settings"]
        return user

class UserManager:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.users_dir = self.data_dir / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.users: Dict[str, User] = self._load_users()

    def _load_users(self) -> Dict[str, User]:
        users = {}
        for user_file in self.users_dir.glob("*.json"):
            with open(user_file, 'r') as f:
                user_data = json.load(f)
                user = User.from_dict(user_data)
                users[user.user_id] = user
        return users

    def create_user(self, username: str, email: str, password: str) -> User:
        # Check if username or email already exists
        if any(u.username == username for u in self.users.values()):
            raise ValueError(f"Username '{username}' already exists")
        if any(u.email == email for u in self.users.values()):
            raise ValueError(f"Email '{email}' already exists")

        # Create new user
        user = User(username=username, email=email)
        
        # Hash password
        password_hash = self._hash_password(password)
        
        # Save user data
        user_data = user.to_dict()
        user_data["password_hash"] = password_hash
        
        user_file = self.users_dir / f"{user.user_id}.json"
        with open(user_file, 'w') as f:
            json.dump(user_data, f, indent=2)
        
        # Create user-specific directories
        self._create_user_directories(user.user_id)
        
        self.users[user.user_id] = user
        return user

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        user = next((u for u in self.users.values() if u.username == username), None)
        if not user:
            return None

        user_file = self.users_dir / f"{user.user_id}.json"
        with open(user_file, 'r') as f:
            user_data = json.load(f)

        if self._verify_password(password, user_data["password_hash"]):
            return user
        return None

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def update_user_settings(self, user_id: str, settings: Dict) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False

        user.settings.update(settings)
        user_file = self.users_dir / f"{user_id}.json"
        with open(user_file, 'r') as f:
            user_data = json.load(f)
        
        user_data["settings"] = user.settings
        
        with open(user_file, 'w') as f:
            json.dump(user_data, f, indent=2)
        
        return True

    def _create_user_directories(self, user_id: str):
        """Create necessary directories for user data"""
        user_data_dir = self.data_dir / user_id
        (user_data_dir / "downloads").mkdir(parents=True, exist_ok=True)
        (user_data_dir / "transcripts").mkdir(parents=True, exist_ok=True)
        (user_data_dir / "summaries").mkdir(parents=True, exist_ok=True)

    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against stored hash"""
        return self._hash_password(password) == password_hash 