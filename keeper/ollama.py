"""Small asynchronous Ollama client; leaving chat_stream closes the response."""
from __future__ import annotations

import json

import httpx


class Ollama:
    def __init__(self, base_url="http://127.0.0.1:11434", model="qwen3.5:2b",
                 transport=None, num_ctx=8192):
        self.model, self.num_ctx = model, num_ctx
        self.client = httpx.AsyncClient(base_url=base_url, transport=transport, timeout=None,
                                       follow_redirects=False)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.client.aclose()

    def payload(self, messages, tools, stream, num_predict):
        return {"model": self.model, "messages": messages, "tools": tools, "stream": stream,
                "think": False, "options": {"temperature": 0.2, "num_predict": num_predict,
                                             "num_ctx": self.num_ctx}}

    @staticmethod
    def checked(response):
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("error"):
            raise ValueError("Invalid Ollama response")
        return data

    async def chat(self, messages, tools, num_predict=700):
        return self.checked(await self.client.post(
            "/api/chat", json=self.payload(messages, tools, False, num_predict)))

    async def chat_stream(self, messages, tools, num_predict=700):
        async with self.client.stream("POST", "/api/chat", json=self.payload(
                messages, tools, True, num_predict)) as response:
            response.raise_for_status()
            done = False
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                data = json.loads(line)
                if not isinstance(data, dict) or data.get("error"):
                    raise ValueError("Invalid Ollama stream")
                yield data
                if data.get("done"):
                    done = True
                    break
            if not done:
                raise ValueError("Incomplete Ollama stream")

    async def digest(self):
        data = self.checked(await self.client.get("/api/tags"))
        names = {self.model, self.model + ":latest"} if ":" not in self.model else {self.model}
        return next((m.get("digest") for m in data.get("models", [])
                     if m.get("name", m.get("model")) in names), None)

    async def show(self):
        data = self.checked(await self.client.post("/api/show", json={"model": self.model}))
        return {**data, "digest": await self.digest()}

    async def ps(self):
        return self.checked(await self.client.get("/api/ps"))
