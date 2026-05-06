"""Basic usage example for py-ai."""
from dotenv import load_dotenv
import os

from jay_llm import LLM

load_dotenv()
def main():
    """Run basic examples."""
    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    provider = os.getenv("OPENAI_PROVIDER", "openai")  # 默认 openai
    model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    if not api_key:
        print("Please set OPENAI_API_KEY environment variable")
        return

    # Initialize LLM
    llm = LLM(provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,)

    # Simple completion
    print("=== Simple Completion ===")
    response = llm.complete("What is Python?")
    print(response.content)
    print(f"\nTokens used: {response.usage['total_tokens']}")

    # With system message
    print("\n=== With System Message ===")
    response = llm.complete(
        "Translate 'Hello, world!' to Spanish",
        system="You are a helpful translator",
    )
    print(response.content)

    # Streaming
    print("\n=== Streaming ===")
    for chunk in llm.stream("Count from 1 to 15"):
        print(chunk.content, end="", flush=True)
    print()


if __name__ == "__main__":
    main()
