from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        env_ignore_empty=True,  # empty keys in .env fall back to defaults
    )

    openai_api_key: str = ""
    vision_link: str = Field(default="", validation_alias="SWINV2_AND_SEGFORMER_LINK")
    vision_mode: Literal["live", "mock"] = "live"
    google_client_id: str = ""
    session_secret: str = "dev-insecure-change-me"

    model: str = Field(default="gpt-4o-mini", validation_alias="CONSILIUM_MODEL")
    critic_max_rounds: int = Field(default=3, validation_alias="CRITIC_MAX_ROUNDS")