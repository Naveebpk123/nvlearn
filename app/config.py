import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(24)
    SQLALCHEMY_DATABASE_URI = "sqlite:///notes.db"
    SEND_FILE_MAX_AGE_DEFAULT = 0
    VERIFICATION_TTL_SECONDS = 10 * 60
    NOTE_ACTION_COOLDOWN_SECONDS = 5 * 60
    MAX_CONTENT_CHAR_LIMIT = 30000
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024 
    DEFAULT_TAGS = [
        "personal", "mathematics", "science", "history", "computer science",
        "literature", "physics", "biology", "chemistry", "math",
    ]