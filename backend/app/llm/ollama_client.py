"""Thin Ollama HTTP client (chat streaming, JSON generation, embeddings, model listing)."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.core.config import get_settings


class OllamaError(Exception):
    pass


def _base() -> str:
    return get_settings().ollama_url.rstrip("/")


def _raise(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("error", resp.text)
        except Exception:  # noqa: BLE001
            detail = resp.text
        raise OllamaError(f"Ollama {resp.status_code}: {detail}")


def embed_sync(texts: list[str], model: str, timeout: float = 300) -> list[list[float]]:
    try:
        resp = httpx.post(f"{_base()}/api/embed", json={"model": model, "input": texts, "truncate": True},
                          timeout=timeout)
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama injoignable ({_base()}) : {exc}") from exc
    _raise(resp)
    data = resp.json()
    return data["embeddings"]


async def chat_stream(model: str, messages: list[dict], options: dict[str, Any]) -> AsyncIterator[str]:
    payload = {"model": model, "messages": messages, "stream": True, "options": options, "keep_alive": "30m"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=10)) as client:
            async with client.stream("POST", f"{_base()}/api/chat", json=payload) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                    _raise(resp)
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise OllamaError(chunk["error"])
                    piece = chunk.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if chunk.get("done"):
                        break
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama injoignable ({_base()}) : {exc}") from exc


async def chat_complete(model: str, messages: list[dict], options: dict[str, Any], json_format: bool = False) -> str:
    payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "options": options, "keep_alive": "30m"}
    if json_format:
        payload["format"] = "json"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=10)) as client:
            resp = await client.post(f"{_base()}/api/chat", json=payload)
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama injoignable ({_base()}) : {exc}") from exc
    _raise(resp)
    return resp.json().get("message", {}).get("content", "")


def list_models() -> list[dict]:
    try:
        resp = httpx.get(f"{_base()}/api/tags", timeout=5)
        _raise(resp)
        return resp.json().get("models", [])
    except httpx.HTTPError as exc:
        raise OllamaError(f"Ollama injoignable ({_base()}) : {exc}") from exc
