from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StreamEvent:
    id: int
    event: str
    data: dict[str, Any]


class EventBroker:
    """In-process fan-out for the monitor's read-only SSE stream.

    Subscribers have bounded queues. A slow browser never blocks the Trading 212
    polling loop; when a queue fills, its oldest pending event is dropped in favor
    of the newest state.
    """

    def __init__(self, queue_size: int = 32) -> None:
        self.queue_size = max(4, int(queue_size))
        self._subscribers: set[asyncio.Queue[StreamEvent]] = set()
        self._sequence = 0
        self.published = 0
        self.dropped = 0

    def subscribe(self) -> asyncio.Queue[StreamEvent]:
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=self.queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[StreamEvent]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: str, data: dict[str, Any]) -> StreamEvent:
        self._sequence += 1
        item = StreamEvent(id=self._sequence, event=event, data=data)
        self.published += 1

        for queue in tuple(self._subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                    self.dropped += 1
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                self.dropped += 1
        return item

    def stats(self) -> dict[str, int]:
        return {
            "subscribers": len(self._subscribers),
            "published": self.published,
            "dropped": self.dropped,
            "last_event_id": self._sequence,
        }


def encode_sse(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    lines: list[str] = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    # JSON emitted above is compact, but splitting keeps this helper valid if a
    # future serializer ever introduces embedded newlines.
    for line in payload.splitlines() or [""]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"
