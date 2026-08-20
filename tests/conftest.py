from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pytest

from stt.config import Settings
from stt.models import TranscriptSegment


class FakeFinishReason(Enum):
    STOP = 'STOP'
    MAX_TOKENS = 'MAX_TOKENS'
    SAFETY = 'SAFETY'


@dataclass
class FakeUsage:
    prompt_token_count: int | None = 0
    candidates_token_count: int | None = 0
    thoughts_token_count: int | None = 0


@dataclass
class FakePart:
    text: str | None = None


@dataclass
class FakeContent:
    parts: list[FakePart] | None = None


@dataclass
class FakeCandidate:
    content: FakeContent | None = None
    finish_reason: Any = None


class FakeResponse:
    """存取 .text 時，若 _text 是 RAISE 會丟 ValueError，用來測 response_text 的 fallback。"""

    RAISE = object()

    def __init__(
        self,
        text: Any = '',
        finish_reason: Any = None,
        candidates: list[FakeCandidate] | None = None,
        usage_metadata: Any = None,
    ) -> None:
        self._text = text
        self.candidates = candidates
        self.usage_metadata = usage_metadata
        if candidates is None and finish_reason is not None:
            self.candidates = [FakeCandidate(finish_reason=finish_reason)]

    @property
    def text(self) -> Any:
        if self._text is FakeResponse.RAISE:
            raise ValueError('response has no text')
        return self._text


@dataclass
class FakeUploadedFile:
    uri: str


class FakeModels:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError('FakeClient 的回應已用完')
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeFiles:
    def __init__(self, uri_prefix: str = 'files/fake') -> None:
        self._uri_prefix = uri_prefix
        self.uploaded: list[str] = []

    def upload(self, *, file: str) -> FakeUploadedFile:
        self.uploaded.append(file)
        return FakeUploadedFile(uri=f'{self._uri_prefix}/{len(self.uploaded)}')


class FakeClient:
    def __init__(self, responses: list[Any] | tuple = (), uri_prefix: str = 'files/fake') -> None:
        self.models = FakeModels(list(responses))
        self.files = FakeFiles(uri_prefix)


@dataclass
class RunRecorder:
    """記錄 stt.audio._run 收到的指令，並依序回傳事先排好的 CompletedProcess。"""

    results: list[subprocess.CompletedProcess] = field(default_factory=list)
    commands: list[list[str]] = field(default_factory=list)
    default: subprocess.CompletedProcess | None = None

    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess:
        self.commands.append(cmd)
        if self.results:
            return self.results.pop(0)
        if self.default is not None:
            return self.default
        raise AssertionError('RunRecorder 的結果已用完')


def completed(stdout: str = '', stderr: str = '', returncode: int = 0):
    return subprocess.CompletedProcess(
        args=['ffmpeg'], returncode=returncode, stdout=stdout, stderr=stderr
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gemini_transient_retries=2,
        gemini_transient_retry_delay=0,
        max_chunk_continuations=3,
        premature_stop_retries=1,
    )


@pytest.fixture
def segment():
    def _make(
        speaker: str = 'Speaker 1',
        timestamp: str = '00:01',
        content: str = 'hello',
        lang_code: str = 'zh',
    ) -> TranscriptSegment:
        return TranscriptSegment(
            speaker=speaker, timestamp=timestamp, content=content, lang_code=lang_code
        )

    return _make


@pytest.fixture
def segments_json():
    import json

    def _make(segments: list[TranscriptSegment]) -> str:
        return json.dumps(
            {'segments': [seg.model_dump(mode='json') for seg in segments]}, ensure_ascii=False
        )

    return _make


@pytest.fixture
def fake_client():
    def _make(responses: list[Any] | tuple = (), uri_prefix: str = 'files/fake') -> FakeClient:
        return FakeClient(responses, uri_prefix)

    return _make


@pytest.fixture
def fake_run(monkeypatch):
    """monkeypatch stt.audio._run，回傳 RunRecorder 讓測試設定結果與檢查指令。"""

    def _install(
        results: list[subprocess.CompletedProcess] | None = None,
        default: subprocess.CompletedProcess | None = None,
    ) -> RunRecorder:
        recorder = RunRecorder(results=list(results or []), default=default)
        monkeypatch.setattr('stt.audio._run', recorder)
        return recorder

    return _install


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept: list[float] = []
    monkeypatch.setattr('stt.utils.time.sleep', lambda seconds: slept.append(seconds))
    return slept


@pytest.fixture(autouse=True)
def isolated_logging():
    logger = logging.getLogger('stt')
    handlers = list(logger.handlers)
    level = logger.level
    propagate = logger.propagate
    yield logger
    for handler in logger.handlers:
        handler.close()
    logger.handlers = handlers
    logger.setLevel(level)
    logger.propagate = propagate
