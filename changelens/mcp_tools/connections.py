from changelens.config import Settings
from langchain_mcp_adapters.sessions import Connection


ALLOWED_TOOLS: dict[str,frozenset[str]] = {
    "context7" : frozenset({"resolve-library-id","query-docs"}),
    "github": frozenset({
        "get_file_contents","search_code","list_commits","get_commit","pull_request_read","list_branches"
    }),
    "tavily": frozenset({
        "tavily_search"
    })
    }

def build_connections(settings: Settings) -> dict[str, Connection]:
    connections: dict[str, Connection] = {}
    
    if settings.context7_api_key is not None:
        connections["context7"] ={
            "transport": "streamable_http",
            "url": settings.context7_mcp_url,
            "timeout": settings.mcp_connection_timeout,
            "headers": {
                "CONTEXT7_API_KEY": settings.context7_api_key.get_secret_value()
            },
        }
    if settings.tavily_api_key is not None:
        connections["tavily"]={
            "transport": "streamable_http",
            "url": settings.tavily_mcp_url,
            "timeout": settings.mcp_connection_timeout,
            "headers":{
                "Authorization": f"Bearer {settings.tavily_api_key.get_secret_value()}"
                
            }
        }
    if settings.github_pat is not None:
        connections["github"] = {
            "transport": 'streamable_http',
            "url": settings.github_mcp_url,
            "timeout": settings.mcp_connection_timeout,
            "headers":{
                "Authorization": f"Bearer {settings.github_pat.get_secret_value()}",
                "X-MCP-Readonly": "true"
            }
        }

    return connections
    
    


