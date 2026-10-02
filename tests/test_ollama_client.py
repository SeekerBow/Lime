"""ai.ollama_client 单元测试：用假 session 验证请求构造与错误处理。"""

import json

import pytest
import requests

from lime.ai.ollama_client import DEFAULT_HOST, OllamaClient, OllamaError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, lines=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self._lines = lines or []
        self.text = text
        self.closed = False

    def json(self):
        if self._payload is None:
            raise ValueError("invalid json")
        return self._payload

    def iter_lines(self):
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls: list = []

    def request(self, method, url, json=None, timeout=None):
        self.calls.append((method, url, json, timeout))
        if self.exc is not None:
            raise self.exc
        return self.response

    def post(self, url, json=None, timeout=None, stream=False):
        self.calls.append(("POST", url, json, timeout, stream))
        if self.exc is not None:
            raise self.exc
        return self.response


def make_client(session):
    return OllamaClient(host="http://127.0.0.1:11434", timeout=5, session=session)


def test_default_host():
    client = OllamaClient()
    assert client.host == DEFAULT_HOST


def test_host_normalized_without_scheme():
    client = OllamaClient(host="127.0.0.1:11434")
    assert client.host == "http://127.0.0.1:11434"


def test_host_strips_trailing_slash():
    client = OllamaClient(host="http://127.0.0.1:11434/")
    assert client.host == "http://127.0.0.1:11434"


def test_empty_host_falls_back_to_default():
    assert OllamaClient(host="").host == DEFAULT_HOST
    assert OllamaClient(host=None).host == DEFAULT_HOST


def test_list_models():
    resp = FakeResponse(payload={"models": [{"name": "qwen:7b"}, {"name": "llama3:8b"}]})
    session = FakeSession(resp)
    client = make_client(session)
    assert client.list_models() == ["qwen:7b", "llama3:8b"]
    method, url, _, _ = session.calls[0]
    assert method == "GET"
    assert url.endswith("/api/tags")


def test_chat_streaming_ndjson():
    lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        json.dumps({"message": {"content": " world"}, "done": False}),
        json.dumps({"done": True}),
    ]
    session = FakeSession(FakeResponse(lines=lines))
    client = make_client(session)
    chunks = list(client.chat([{"role": "user", "content": "hi"}], "qwen:7b"))
    assert chunks == ["Hello", " world"]
    _post, url, payload, _timeout, stream = session.calls[0]
    assert url.endswith("/api/chat")
    assert payload["model"] == "qwen:7b"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]
    assert stream is True


def test_chat_once():
    resp = FakeResponse(payload={"message": {"content": "完整回答"}})
    session = FakeSession(resp)
    client = make_client(session)
    text = client.chat_once([{"role": "user", "content": "q"}], "m")
    assert text == "完整回答"
    method, _url, payload, _timeout = session.calls[0]
    assert method == "POST"
    assert payload["stream"] is False


def test_http_error_raises():
    session = FakeSession(FakeResponse(status_code=500, text="boom"))
    client = make_client(session)
    with pytest.raises(OllamaError, match="500"):
        client.list_models()


def test_connection_error_raises():
    session = FakeSession(exc=requests.ConnectionError("refused"))
    client = make_client(session)
    with pytest.raises(OllamaError, match="无法连接"):
        client.list_models()


def test_stream_http_error_raises():
    session = FakeSession(FakeResponse(status_code=404, text="not found"))
    client = make_client(session)
    with pytest.raises(OllamaError, match="404"):
        list(client.chat([], "m"))


def test_bad_json_raises():
    session = FakeSession(FakeResponse(payload=None))
    client = make_client(session)
    with pytest.raises(OllamaError):
        client.list_models()


def test_empty_lines_ignored():
    lines = ["", json.dumps({"message": {"content": "x"}, "done": True}), ""]
    session = FakeSession(FakeResponse(lines=lines))
    client = make_client(session)
    assert list(client.chat([], "m")) == ["x"]
