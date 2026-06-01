from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "GraphRAG System"
    ENV: str = "development"  # development | production
    DEBUG: bool = True

    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    STATIC_DIR: Path = BASE_DIR / "app" / "static"
    DATA_DIR: Path = BASE_DIR / "data"
    DOCUMENT_UPLOAD_DIR: Path = DATA_DIR / "documents"
    MAX_DOCUMENT_UPLOAD_MB: int = 100

    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Kùzu & LanceDB
    KUZU_DB_PATH: Path = Path("data/kuzu/graph.db")
    LANCEDB_PATH: Path = Path("data/lancedb")
    VECTOR_INDEX_TABLE: str = "document_chunks"
    VECTOR_DISTANCE_METRIC: str = "cosine"

    # LLM
    OPENAI_API_KEY: str = ""

    # Embedding
    EMBEDDING_PROVIDER: str = "local_hashing"
    EMBEDDING_MODEL_NAME: str = "local-hashing-v1"
    EMBEDDING_DIMENSIONS: int = 384
    RETRIEVAL_MIN_SCORE: float = 0.0

    # End-user chat grounding
    CHAT_MIN_GROUNDED_SIMILARITY: float = 0.55
    CHAT_CONTEXT_TOTAL_CHAR_LIMIT: int = 12_000
    CHAT_CONTEXT_PER_CHUNK_CHAR_LIMIT: int = 1_800
    CHAT_CONTEXT_MAX_BLOCKS: int = 8

    # Security
    SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    # CORS (cho việc embed iframe)
    ALLOWED_ORIGINS: list[str] = ["*"]


settings = Settings()
