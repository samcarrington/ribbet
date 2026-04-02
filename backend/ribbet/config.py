"""Application configuration."""

from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    """App-wide settings."""

    app_data_dir: Path = Path.home() / ".ribbet"
    db_filename: str = "ribbet.db"
    host: str = "127.0.0.1"
    port: int = 8000
    stt_model_repo: str = "kyutai/stt-1b-en_fr"
    stt_quantization: int = 4
    insight_model: str = "mlx-community/Qwen2.5-3B-Instruct-4bit"
    insight_window_seconds: int = 120
    insight_refresh_seconds: int = 30
    bookmark_snippet_seconds: int = 30

    @property
    def db_path(self) -> Path:
        return self.app_data_dir / self.db_filename


settings = Settings()
