"""CLI entry point for jay-web-ui."""

import os
import sys

try:
    import typer
    from rich.console import Console
except ImportError:
    print("Error: Required dependencies not installed")
    print("Run: pip install jay-web-ui")
    sys.exit(1)

try:
    from jay_llm import LLM
except ImportError:
    print("Error: jay-llm not installed")
    print("Run: pip install jay-llm")
    sys.exit(1)

from .server import ChatServer

console = Console()


def _load_env():
    """Load .env file from CWD or project root."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


def main(
    model: str | None = None,
    provider: str | None = None,
    port: int | None = None,
    host: str | None = None,
    cors: bool = False,
    title: str | None = None,
):
    """Start web chat server.

    Args:
        model: LLM model to use
        provider: LLM provider (openai, anthropic, google)
        port: Server port
        host: Server host
        cors: Enable CORS
        title: Chat title
    """
    _load_env()

    provider = provider or os.getenv("LLM_PROVIDER", "openai")
    model = model or os.getenv("LLM_MODEL")
    port = port or int(os.getenv("PORT", "8000"))
    host = host or os.getenv("HOST", "127.0.0.1")
    title = title or os.getenv("CHAT_TITLE", "Chat")
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    temperature = os.getenv("LLM_TEMPERATURE")

    # Get API key: provider-specific first, then generic fallback
    api_key = os.getenv(f"{provider.upper()}_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        console.print(f"[red]Error: {provider.upper()}_API_KEY not set[/red]")
        console.print(f"Please set your API key in .env or environment:")
        console.print(f"  {provider.upper()}_API_KEY=your-key-here")
        sys.exit(1)

    # Create LLM
    kwargs = {"provider": provider, "api_key": api_key}
    if model:
        kwargs["model"] = model
    elif provider == "openai":
        kwargs["model"] = "gpt-3.5-turbo"
    if base_url:
        kwargs["base_url"] = base_url
    if temperature:
        kwargs["temperature"] = float(temperature)

    try:
        llm = LLM(**kwargs)
    except Exception as e:
        console.print(f"[red]Error creating LLM: {e}[/red]")
        sys.exit(1)

    # Create server
    server = ChatServer(
        llm=llm,
        title=title,
        port=port,
        host=host,
        cors=cors,
    )

    # Print info
    console.print("[green]✓ Web UI Server started[/green]")
    console.print(f"Model: [cyan]{llm.config.model}[/cyan]")
    if base_url:
        console.print(f"Base URL: [cyan]{base_url}[/cyan]")
    console.print(f"URL: [cyan]http://{host}:{port}[/cyan]")
    console.print()
    console.print("Press Ctrl+C to stop")

    # Run server
    try:
        server.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped[/yellow]")


def cli():
    """Entry point for jay-webui command."""
    typer.run(main)


if __name__ == "__main__":
    cli()
