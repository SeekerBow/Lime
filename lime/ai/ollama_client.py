# Copyright (C) 2026 SeekerBow
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Ollama HTTP 客户端（纯 requests 封装，可脱离 Qt 测试）。

接口对应本地 Ollama：
- ``GET  /api/tags``  列出本地模型
- ``POST /api/chat``  多轮对话（支持流式 NDJSON）
"""

from __future__ import annotations

import json
from typing import Iterator, Optional

import requests

DEFAULT_HOST = "http://127.0.0.1:11434"


class OllamaError(Exception):
    """Ollama 调用失败（网络错误、非 200、返回体非法）。"""


def _normalize_host(host: str) -> str:
    """补全协议头并去除末尾斜杠，容忍用户只填写 ``127.0.0.1:11434``。"""
    host = (host or DEFAULT_HOST).strip().rstrip("/")
    if not host:
        return DEFAULT_HOST
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host


class OllamaClient:
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        timeout: int = 60,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.host = _normalize_host(host)
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()

    # ---- 模型列表 --------------------------------------------------------
    def list_models(self) -> list[str]:
        """返回已安装模型名称列表，如 ``["qwen2.5-coder:7b"]``。"""
        data = self._request("GET", "/api/tags")
        models = data.get("models", []) if isinstance(data, dict) else []
        return [str(m.get("name", "")) for m in models if m.get("name")]

    # ---- 对话 ------------------------------------------------------------
    def chat(
        self,
        messages: list[dict],
        model: str,
        stream: bool = True,
    ) -> Iterator[str]:
        """流式对话生成器，逐块 yield 文本增量。

        messages 形如 ``[{"role": "user", "content": "..."}]``。
        失败时抛 :class:`OllamaError`。
        """
        payload = {"model": model, "messages": messages, "stream": True}
        response = self._raw_post("/api/chat", payload, stream=True)
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                content = (chunk.get("message") or {}).get("content") or ""
                if content:
                    yield content
                if chunk.get("done"):
                    break
        finally:
            response.close()

    def chat_once(self, messages: list[dict], model: str) -> str:
        """非流式对话，返回完整回复。"""
        payload = {"model": model, "messages": messages, "stream": False}
        data = self._request("POST", "/api/chat", json=payload)
        return str((data.get("message") or {}).get("content") or "")

    # ---- 底层 HTTP -------------------------------------------------------
    def _request(self, method: str, path: str, json=None) -> dict:
        try:
            response = self.session.request(
                method,
                self.host + path,
                json=json,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise OllamaError(f"无法连接 Ollama（{self.host}）：{exc}") from exc
        if response.status_code != 200:
            raise OllamaError(
                f"Ollama 返回 {response.status_code}：{response.text[:200]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise OllamaError(f"Ollama 返回了无法解析的 JSON：{exc}") from exc

    def _raw_post(self, path: str, payload: dict, stream: bool):
        try:
            response = self.session.post(
                self.host + path,
                json=payload,
                timeout=self.timeout,
                stream=stream,
            )
        except requests.RequestException as exc:
            raise OllamaError(f"无法连接 Ollama（{self.host}）：{exc}") from exc
        if response.status_code != 200:
            body = response.text[:200]
            response.close()
            raise OllamaError(f"Ollama 返回 {response.status_code}：{body}")
        return response
