"""GLM provider using native zai-sdk."""

from collections.abc import AsyncIterator, Iterator

from ..config import Config
from ..models import Message, Response, StreamChunk
from ._base import Provider


class GLMProvider(Provider):
    """GLM provider using native zai-sdk."""

    def __init__(self, config: Config):
        """Initialize GLM provider."""
        try:
            from zai import ZhipuAiClient
        except ImportError:
            raise ImportError(
                "zai-sdk is required for GLM provider. "
                "Install it with: pip install zai-sdk"
            )

        self.config = config
        self.client = ZhipuAiClient(api_key=config.api_key)

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal messages to GLM format."""
        result = []
        for msg in messages:
            if msg.role == "assistant" and msg.metadata and "tool_calls" in msg.metadata:
                result.append(
                    {
                        "role": "assistant",
                        "content": msg.content or None,
                        "tool_calls": msg.metadata["tool_calls"],
                    }
                )
            elif msg.role == "tool" and msg.metadata:
                result.append(
                    {
                        "role": "tool",
                        "content": msg.content,
                        "tool_call_id": msg.metadata.get("tool_call_id", ""),
                    }
                )
            else:
                result.append({"role": msg.role, "content": msg.content})
        return result

    @staticmethod
    def _extract_tool_calls(message) -> list[dict] | None:
        """Extract tool_calls from response message."""
        if not hasattr(message, "tool_calls") or not message.tool_calls:
            return None
        return [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]

    def complete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Generate a completion."""
        if "tools" in kwargs and kwargs["tools"]:
            kwargs.setdefault("tool_choice", "auto")

        response = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }

        return Response(
            content=choice.message.content or "",
            model=response.model,
            usage=usage,
            finish_reason=choice.finish_reason,
            tool_calls=self._extract_tool_calls(choice.message),
            metadata={"id": response.id},
        )

    def stream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Iterator[StreamChunk]:
        """Stream a completion."""
        if "tools" in kwargs and kwargs["tools"]:
            kwargs.setdefault("tool_choice", "auto")
            kwargs.setdefault("tool_stream", True)

        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.delta.content:
                yield StreamChunk(
                    content=choice.delta.content,
                    finish_reason=choice.finish_reason,
                    metadata={"id": chunk.id},
                )

    async def acomplete(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> Response:
        """Async generate a completion."""
        # zai-sdk doesn't have async support, use sync version
        return self.complete(messages, model, temperature, max_tokens, **kwargs)

    async def astream(
        self,
        messages: list[Message],
        model: str,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Async stream a completion."""
        if "tools" in kwargs and kwargs["tools"]:
            kwargs.setdefault("tool_choice", "auto")
            kwargs.setdefault("tool_stream", True)

        stream = self.client.chat.completions.create(
            model=model,
            messages=self._convert_messages(messages),
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        # Accumulate tool calls
        final_tool_calls = {}

        for chunk in stream:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Yield content
            if hasattr(delta, 'content') and delta.content:
                yield StreamChunk(
                    content=delta.content,
                    finish_reason=chunk.choices[0].finish_reason,
                    metadata={"id": chunk.id},
                )

            # Accumulate tool calls
            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    index = tool_call.index
                    if index not in final_tool_calls:
                        final_tool_calls[index] = {
                            "id": tool_call.id if hasattr(tool_call, 'id') else f"call_{index}",
                            "name": "",
                            "arguments": ""
                        }

                    if hasattr(tool_call, 'function'):
                        if hasattr(tool_call.function, 'name') and tool_call.function.name:
                            final_tool_calls[index]["name"] = tool_call.function.name
                        if hasattr(tool_call.function, 'arguments') and tool_call.function.arguments:
                            final_tool_calls[index]["arguments"] += tool_call.function.arguments

        # Yield accumulated tool calls at the end
        if final_tool_calls:
            # Convert to standard format
            tool_calls_list = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"]
                    }
                }
                for tc in final_tool_calls.values()
            ]

            # Create a special chunk with tool calls
            yield StreamChunk(
                content="",
                finish_reason="tool_calls",
                tool_calls=tool_calls_list,
                metadata={},
            )
