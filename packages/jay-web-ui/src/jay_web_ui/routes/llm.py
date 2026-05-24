"""LLM-related endpoints: model listing, model swap, vision-model toggle, config."""

from __future__ import annotations

from fastapi import Request


def register(server) -> None:
    """Mount LLM endpoints onto ``server.app``."""

    @server.app.get("/api/models")
    async def get_models():
        """获取当前 API 可用的模型列表"""
        llm = _resolve_llm(server)
        if not llm or not hasattr(llm, "config"):
            return {"models": [], "current": "unknown"}
        try:
            import httpx
            base_url = (llm.config.base_url or "https://api.openai.com/v1").rstrip("/")
            headers = {"Authorization": f"Bearer {llm.config.api_key}"}
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{base_url}/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                models.sort()
                return {"models": models, "current": llm.config.model}
        except Exception as e:
            return {"models": [llm.config.model], "current": llm.config.model, "error": str(e)}

    @server.app.post("/api/model")
    async def set_model(request: Request):
        """切换当前使用的模型"""
        body = await request.json()
        new_model = body.get("model", "").strip()
        if not new_model:
            return {"status": "error", "error": "model is required"}

        llm = _resolve_llm(server)
        if not llm:
            return {"status": "error", "error": "No LLM configured"}

        from jay_llm import LLM
        new_llm = LLM(
            provider=llm.config.provider,
            api_key=llm.config.api_key,
            model=new_model,
            base_url=llm.config.base_url,
            temperature=llm.config.temperature,
        )

        if server.agent:
            if hasattr(server.agent, "agent") and hasattr(server.agent.agent, "llm"):
                server.agent.agent.llm = new_llm
            elif hasattr(server.agent, "llm"):
                server.agent.llm = new_llm
        elif server.llm:
            server.llm = new_llm

        return {"status": "ok", "model": new_model}

    @server.app.get("/api/vision-model")
    async def get_vision_model():
        """Get the configured vision fallback model."""
        return {"vision_model": server.vision_model}

    @server.app.post("/api/vision-model")
    async def set_vision_model(request: Request):
        """Set the vision fallback model for image understanding."""
        body = await request.json()
        model = (body.get("model") or "").strip()
        server.vision_model = model or None
        return {"status": "ok", "vision_model": server.vision_model}

    @server.app.get("/api/config")
    async def get_config():
        """返回当前 LLM 配置（隐藏 API Key）"""
        llm = _resolve_llm(server)
        if not llm or not hasattr(llm, "config"):
            return {}
        cfg = llm.config
        return {
            "provider": cfg.provider,
            "model": cfg.model,
            "base_url": cfg.base_url or "（默认）",
            "temperature": cfg.temperature,
            "max_tokens": cfg.max_tokens or "（不限）",
        }


def _resolve_llm(server):
    if server.agent:
        if hasattr(server.agent, "agent") and hasattr(server.agent.agent, "llm"):
            return server.agent.agent.llm
        if hasattr(server.agent, "llm"):
            return server.agent.llm
    return server.llm
