"""Recipe 09: streaming responses with user-triggered cancellation.

Production chat UIs must:

- stream tokens to the user as they arrive,
- let the user click "Stop",
- preserve whatever the model produced up to the moment of cancellation.

This recipe implements that pattern on top of Anthropic's streaming API.
The key abstraction is ``StreamSession``: a small stateful object that owns
a cancellation token, buffers partial text, and exposes an iterator the UI
drives. Calling ``session.cancel()`` from any thread (or signal handler)
stops token accumulation and preserves whatever has been produced so far.

We do not rely on HTTP socket closure for correctness. Instead we drive the
SDK's streaming iterator and stop consuming events once ``cancel()`` is
called. The underlying HTTP connection is closed by the SDK's context
manager when we exit the ``with`` block.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from common.client import CookbookClient
from common.logging import get_logger, setup_logging

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@dataclass
class StreamSession:
    """Owns a single streaming response's lifecycle.

    The session is thread-safe for ``cancel()``. The consumer typically runs
    on one thread (or async task) and the UI calls ``cancel()`` from
    another.
    """

    buffer: list[str] = field(default_factory=list)
    cancelled: bool = False
    stop_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    cancel_at: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, text: str) -> None:
        with self._lock:
            self.buffer.append(text)

    def cancel(self) -> None:
        with self._lock:
            if not self.cancelled:
                self.cancelled = True
                self.cancel_at = time.monotonic()

    @property
    def text(self) -> str:
        with self._lock:
            return "".join(self.buffer)

    def is_cancelled(self) -> bool:
        with self._lock:
            return self.cancelled


# ---------------------------------------------------------------------------
# Streaming driver
# ---------------------------------------------------------------------------


def _event_attr(event: Any, name: str) -> Any:
    if isinstance(event, dict):
        return event.get(name)
    return getattr(event, name, None)


def _text_delta_from_event(event: Any) -> str | None:
    """Return the text delta for a ``content_block_delta`` event, else None."""
    if _event_attr(event, "type") != "content_block_delta":
        return None
    delta = _event_attr(event, "delta") or {}
    if _event_attr(delta, "type") != "text_delta":
        return None
    text = _event_attr(delta, "text")
    return text if isinstance(text, str) else None


def _usage_from_message_delta(event: Any) -> dict[str, Any]:
    if _event_attr(event, "type") not in {"message_delta", "message_stop"}:
        return {}
    usage = _event_attr(event, "usage") or {}
    if isinstance(usage, dict):
        return dict(usage)
    return {
        "input_tokens": _event_attr(usage, "input_tokens") or 0,
        "output_tokens": _event_attr(usage, "output_tokens") or 0,
    }


def stream_response(
    client: CookbookClient,
    *,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 1024,
    on_text: Callable[[str], None] | None = None,
    session: StreamSession | None = None,
    event_source: Iterable[Any] | None = None,
) -> StreamSession:
    """Stream ``prompt`` into ``session``, stopping if ``session.cancel()`` is called.

    ``event_source`` exists for tests: if provided, we iterate it as if it
    were the SDK's streaming iterator. In production, it is None and the
    SDK's ``messages.stream`` context manager is used.
    """
    session = session or StreamSession()

    if event_source is not None:
        _drive(event_source, session=session, on_text=on_text)
        return session

    with client.raw.messages.stream(
        model=client.default_model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        _drive(stream, session=session, on_text=on_text)
    return session


def _drive(
    events: Iterable[Any],
    *,
    session: StreamSession,
    on_text: Callable[[str], None] | None,
) -> None:
    for event in events:
        if session.is_cancelled():
            session.stop_reason = "cancelled"
            return
        delta = _text_delta_from_event(event)
        if delta:
            session.append(delta)
            if on_text is not None:
                on_text(delta)
            continue
        etype = _event_attr(event, "type")
        if etype == "message_delta":
            # Capture stop_reason / usage hints from message_delta
            md_delta = _event_attr(event, "delta") or {}
            stop = _event_attr(md_delta, "stop_reason")
            if stop:
                session.stop_reason = stop
            session.usage.update(_usage_from_message_delta(event))
        elif etype == "message_stop":
            session.usage.update(_usage_from_message_delta(event))
            if session.stop_reason is None:
                session.stop_reason = "end_turn"
            return


# ---------------------------------------------------------------------------
# CLI driver (interruptible via stdin "STOP")
# ---------------------------------------------------------------------------


def _run_with_timed_cancel(
    client: CookbookClient,
    *,
    prompt: str,
    deadline_seconds: float,
) -> StreamSession:
    session = StreamSession()

    def timer() -> None:
        time.sleep(deadline_seconds)
        session.cancel()

    thread = threading.Thread(target=timer, daemon=True)
    thread.start()

    def on_text(chunk: str) -> None:
        sys.stdout.write(chunk)
        sys.stdout.flush()

    stream_response(client, prompt=prompt, on_text=on_text, session=session)
    return session


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Recipe 09 — streaming with interruption")
    parser.add_argument("--prompt", default="Explain prompt caching in 200 words.")
    parser.add_argument(
        "--cancel-after",
        type=float,
        default=0.0,
        help="Cancel after N seconds. 0 disables the timer.",
    )
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    setup_logging()
    client = CookbookClient()
    if args.cancel_after > 0:
        session = _run_with_timed_cancel(client, prompt=args.prompt, deadline_seconds=args.cancel_after)
    else:
        session = stream_response(client, prompt=args.prompt, on_text=lambda c: sys.stdout.write(c))
    payload = {
        "cancelled": session.cancelled,
        "stop_reason": session.stop_reason,
        "text": session.text,
        "usage": session.usage,
    }
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
