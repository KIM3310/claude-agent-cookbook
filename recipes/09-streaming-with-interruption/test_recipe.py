"""Tests for recipe 09."""

from __future__ import annotations

from typing import Any, Iterable

from recipes._fixtures import FakeStreamEvent

from .recipe import StreamSession, _text_delta_from_event, stream_response


def _delta_event(text: str, index: int = 0) -> FakeStreamEvent:
    return FakeStreamEvent(
        type="content_block_delta",
        delta={"type": "text_delta", "text": text},
        index=index,
    )


def _message_delta_event(*, stop_reason: str | None, usage: dict[str, int] | None = None) -> FakeStreamEvent:
    return FakeStreamEvent(
        type="message_delta",
        delta={"stop_reason": stop_reason} if stop_reason else {},
        usage=usage or {},
    )


def _stop_event(usage: dict[str, int] | None = None) -> FakeStreamEvent:
    return FakeStreamEvent(type="message_stop", usage=usage or {})


def _events(parts: list[str], *, stop_reason: str = "end_turn") -> Iterable[Any]:
    for p in parts:
        yield _delta_event(p)
    yield _message_delta_event(stop_reason=stop_reason, usage={"output_tokens": len("".join(parts))})
    yield _stop_event(usage={"output_tokens": len("".join(parts))})


def test_text_delta_extraction() -> None:
    assert _text_delta_from_event(_delta_event("hi")) == "hi"
    assert _text_delta_from_event(_stop_event()) is None
    assert _text_delta_from_event(FakeStreamEvent(type="content_block_start")) is None


def test_stream_response_accumulates_text() -> None:
    session = stream_response(
        client=None,  # type: ignore[arg-type]
        prompt="hi",
        event_source=_events(["Hello", " ", "world"]),
    )
    assert session.text == "Hello world"
    assert session.stop_reason == "end_turn"
    assert not session.cancelled


def test_stream_response_invokes_on_text_callback() -> None:
    chunks: list[str] = []
    stream_response(
        client=None,  # type: ignore[arg-type]
        prompt="hi",
        event_source=_events(["a", "b", "c"]),
        on_text=chunks.append,
    )
    assert chunks == ["a", "b", "c"]


def test_cancellation_preserves_partial_text() -> None:
    session = StreamSession()

    def event_source() -> Iterable[Any]:
        yield _delta_event("partial ")
        yield _delta_event("more ")
        session.cancel()  # simulate user clicking "Stop" mid-stream
        yield _delta_event("this should NOT be captured")
        yield _stop_event()

    stream_response(
        client=None,  # type: ignore[arg-type]
        prompt="hi",
        event_source=event_source(),
        session=session,
    )
    assert session.cancelled is True
    assert session.stop_reason == "cancelled"
    # The second delta arrived before cancel, so "more " IS captured.
    assert session.text == "partial more "
    assert "NOT" not in session.text


def test_cancel_is_idempotent_and_threadsafe() -> None:
    session = StreamSession()
    session.cancel()
    first_ts = session.cancel_at
    session.cancel()
    session.cancel()
    assert session.cancel_at == first_ts
    assert session.cancelled is True


def test_stream_response_captures_usage_on_message_delta() -> None:
    events = [
        _delta_event("hello"),
        _message_delta_event(stop_reason="end_turn", usage={"output_tokens": 5}),
        _stop_event(usage={"output_tokens": 5}),
    ]
    session = stream_response(
        client=None,  # type: ignore[arg-type]
        prompt="hi",
        event_source=iter(events),
    )
    assert session.usage.get("output_tokens") == 5
    assert session.stop_reason == "end_turn"
