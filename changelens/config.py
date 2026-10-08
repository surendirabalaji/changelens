from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
    )

    llm_api_key: SecretStr | None = None
    github_pat: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    context7_api_key: SecretStr | None = None
    typesafe_api_key: SecretStr | None = None
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b"

    triage_backend: Literal["jev","nemotron"] = "jev"
    gcp_project_id: str | None = None
    gcp_region: str = "us-west1"

    github_mcp_url: str = 'https://api.githubcopilot.com/mcp/'
    context7_mcp_url: str ='https://mcp.context7.com/mcp'
    tavily_mcp_url: str = 'https://mcp.tavily.com/mcp/'



    turn_deadline_s: float = 50.0
    tool_loop_stop_s: float = 30.0
    synthesis_reserve_s: float = 15.0
    triage_timeout_s: float = 2.0
    llm_max_retries: int = 0
    llm_timeout_s: float = 30.0

@lru_cache
def get_settings() -> Settings:
    return Settings()