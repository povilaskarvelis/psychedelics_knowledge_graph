"""Run the same read-only MCP tools over stdio for local agent clients."""

from .config import Settings
from .mcp_server import create_mcp_server
from .r2_sync import sync_from_settings
from .repository import QueryService


def main() -> None:
    settings = Settings.from_env()
    sync_from_settings(settings)
    service = QueryService.from_settings(settings)
    create_mcp_server(service, settings).run(transport="stdio")


if __name__ == "__main__":
    main()
