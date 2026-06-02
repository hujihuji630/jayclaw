import os
import sys
from pathlib import Path


def load_env():
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        example = Path(__file__).parent / ".env.example"
        if example.exists():
            print("提示: 未找到 examples/.env，请复制 .env.example 为 .env 并填写 API Key")
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.split("#")[0].strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), value)


def main():
    load_env()

    try:
        import typer
        from rich.console import Console
    except ImportError:
        print("错误: 缺少依赖，请运行: pip install typer rich")
        sys.exit(1)

    try:
        from jay_llm import LLM
    except ImportError:
        print("错误: jay_llm 未安装，请运行: pip install -e packages/jay-llm")
        sys.exit(1)

    try:
        from jay_coding_agent import CodingAgent
    except ImportError:
        print("错误: jay_coding_agent 未安装，请运行: pip install -e packages/jay-coding-agent")
        sys.exit(1)

    try:
        from jay_web_ui.server import ChatServer
    except ImportError:
        print("错误: jay_web_ui 未安装，请运行: pip install -e packages/jay-web-ui")
        sys.exit(1)

    console = Console()

    provider = os.getenv("LLM_PROVIDER", "openai")
    model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    base_url = os.getenv("LLM_BASE_URL")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "2000")) if os.getenv("LLM_MAX_TOKENS") else None

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "127.0.0.1")
    title = os.getenv("CHAT_TITLE", "JayClaw Chat")

    api_key = os.getenv(f"{provider.upper()}_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        console.print(f"[red]错误: 未设置 API_KEY 或 {provider.upper()}_API_KEY[/red]")
        console.print(f"请运行: export {provider.upper()}_API_KEY=your-api-key")
        sys.exit(1)

    try:
        llm_kwargs = {
            "provider": provider,
            "api_key": api_key,
            "model": model,
            "temperature": temperature,
        }
        if base_url:
            llm_kwargs["base_url"] = base_url
        if max_tokens:
            llm_kwargs["max_tokens"] = max_tokens

        llm = LLM(**llm_kwargs)

        workspace = os.getenv("WORKSPACE", ".")

        agent = CodingAgent(
            llm=llm,
            workspace=workspace,
            verbose=False,
            enable_extensions=True,
            enable_skills=True,
            enable_resilience=False,
            enable_cost_tracking=False,
        )

        if hasattr(agent, 'agent'):
            agent.agent.status_queue = []
    except Exception as e:
        console.print(f"[red]创建 Agent 失败: {e}[/red]")
        sys.exit(1)

    server = ChatServer(agent=agent, title=title, port=port, host=host, cors=True)

    console.print()
    console.print("[bold green]JayClaw Web UI (Coding Agent)[/bold green]")
    console.print("─" * 40)
    console.print(f"  URL:         [cyan]http://{host}:{port}[/cyan]")
    console.print(f"  Provider:    [cyan]{provider}[/cyan]")
    console.print(f"  Model:       [cyan]{llm.config.model}[/cyan]")
    if base_url:
        console.print(f"  Base URL:    [cyan]{base_url}[/cyan]")
    console.print(f"  Temperature: [cyan]{temperature}[/cyan]")
    console.print(f"  Workspace:   [cyan]{Path(workspace).resolve()}[/cyan]")
    console.print("─" * 40)
    console.print("按 [bold]Ctrl+C[/bold] 停止服务器")
    console.print()

    try:
        server.run()
    except KeyboardInterrupt:
        console.print("\n[yellow]服务器已停止[/yellow]")


if __name__ == "__main__":
    main()
