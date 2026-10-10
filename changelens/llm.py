from langchain_openai import ChatOpenAI

from functools import lru_cache

from changelens.config import get_settings

@lru_cache
def get_llm()->ChatOpenAI:
    settings = get_settings()
    if settings.llm_api_key is None:
        raise RuntimeError("LLM_API_KEY is not set")
    return ChatOpenAI(
        model = settings.llm_model,
        temperature= 0.2,
        max_tokens = 2048,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
        api_key = settings.llm_api_key.get_secret_value(),
        base_url= settings.llm_base_url
    )
    