from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

class Settings(BaseSettings):
    GOOGLE_API_KEY: str = Field(..., env="GOOGLE_API_KEY")

    LANGSMITH_API_KEY: str = Field(..., env="LANGSMITH_API_KEY")
    LANGSMITH_PROJECT: str = Field("Maths-TA", env="LANGSMITH_PROJECT")

    CLOUDINARY_CLOUD_NAME: str = Field(..., env="CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY: str = Field(..., env="CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET: str = Field(..., env="CLOUDINARY_API_SECRET")

    PDF_PATH: str = r"C:\Users\chinm\Desktop\GitHub\Maths-TA\ProbabilityForComputerScientists.pdf"
    #Field(..., env="PROBABILITY_FOR_COMPUTER_SCIENTIST_PATH")
    YOUTUBE_PLAYLIST_URL: str = "https://www.youtube.com/playlist?list=PLoROMvodv4rOpr_A7B9SriE_iZmkanvUg"
    #Field(..., env="CS_109_PLAYLIST_URL")
    VIDEO_DIR: str = r"C:\Users\chinm\Desktop\GitHub\Maths-TA\temp_videos"

    HF_TOKEN: str = Field(..., env="HF_TOKEN")

    POSTGRES_DB_URL: str = Field(..., env="POSTGRES_DB_URL")
    # Dimension of the pgvector columns (BAAI/bge-base-en-v1.5)
    VECTOR_DIMENSION: int = 768
    VECTOR_EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    # Optional cross-encoder for re-ranking search hits, off by default. bge-reranker-v2-m3 would take
    # ~35 s per query on this CPU; cross-encoder/ms-marco-MiniLM-L-6-v2 takes ~1.3 s for 20 children.
    RERANKER_MODEL: str = ""
    INGEST_CACHE_DIR: str = ".ingest_cache"
    OLLAMA_API_KEY: str = ""
    OLLAMA_HOST: str = "https://ollama.com"
    OLLAMA_VISION_MODEL: str = "gemma4:31b"
    OLLAMA_TEXT_MODEL: str = "gpt-oss:120b"


    class Config:
        extra = "allow"
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()     