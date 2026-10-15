from functools import lru_cache

from openai import AsyncOpenAI

from app.config import Settings
from app.services.vision_client import HttpVisionClient, MockVisionClient, VisionClient


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_openai() -> AsyncOpenAI:
    key = get_settings().openai_api_key
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured on the server.")
    return AsyncOpenAI(api_key=key)


@lru_cache
def get_vision() -> VisionClient:
    s = get_settings()
    if s.vision_mode == "mock":
        return MockVisionClient()
    return HttpVisionClient(s.vision_link)