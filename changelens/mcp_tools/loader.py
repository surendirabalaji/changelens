import logging
from mcp import ClientSession
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools

from changelens.mcp_tools.guard import guard
from changelens.mcp_tools.connections import ALLOWED_TOOLS

logger = logging.getLogger(__name__)

async def load_allowed_tools(session: ClientSession, server_name: str) -> list[BaseTool]:

    all_tools = await load_mcp_tools(session, server_name=server_name, tool_interceptors=[guard], handle_tool_errors=True)
    
    server_tool_names = {tool.name for tool in all_tools}
    
    allowlist = ALLOWED_TOOLS.get(server_name, [])
    
    for allowed_name in allowlist:
        if allowed_name not in server_tool_names:
            logger.warning(
                f"Allowlisted tool '{allowed_name}' was missing from server '{server_name}'. "
                f"The server implementation may have changed."
            )
            
    filtered_tools = [tool for tool in all_tools if tool.name in allowlist]
    
    return filtered_tools
