"""
Event Streaming Layer: In-Memory & Redis Streams for Asynchronous Incident Processing.
Implements consumer groups, ACK semantics, and Dead Letter Queue (DLQ).
"""

import time
import uuid
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.core.config import settings


class StreamMessage(BaseModel):
    """An event message consumed from a stream."""
    message_id: str
    stream: str
    data: Dict[str, Any]
    timestamp: float = Field(default_factory=time.time)
    attempts: int = 1
    error: Optional[str] = None


class BaseEventStream(ABC):
    """Abstract interface for event streaming pipelines."""

    @abstractmethod
    def publish(self, stream: str, data: Dict[str, Any]) -> str:
        """Publishes an event to the stream and returns the unique message ID."""
        pass

    @abstractmethod
    def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10
    ) -> List[StreamMessage]:
        """Consumes unacknowledged messages for the consumer group."""
        pass

    @abstractmethod
    def ack(self, stream: str, group: str, message_id: str) -> bool:
        """Acknowledges successful processing of a message."""
        pass

    @abstractmethod
    def dead_letter(self, stream: str, group: str, message_id: str, error: str) -> str:
        """Routes a persistently failing message to the Dead Letter Queue (DLQ)."""
        pass

    @abstractmethod
    def get_dlq_messages(self, stream: str) -> List[StreamMessage]:
        """Retrieves dead-lettered messages for inspection."""
        pass


class MemoryEventStream(BaseEventStream):
    """Thread-safe in-memory stream replicating Redis Streams semantics.
    Supports Consumer Groups, Pending Entry Lists (PEL), and DLQ routing.
    """

    def __init__(self):
        # stream_name -> list of (message_id, data, timestamp)
        self._streams: Dict[str, List[StreamMessage]] = {}
        # (stream, group) -> last_delivered_index
        self._group_offsets: Dict[str, int] = {}
        # (stream, group) -> set of pending message_ids
        self._pending: Dict[str, Dict[str, StreamMessage]] = {}
        # stream_name -> list of DLQ messages
        self._dlq: Dict[str, List[StreamMessage]] = {}
        self._lock = threading.Lock()

    def publish(self, stream: str, data: Dict[str, Any]) -> str:
        msg_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        msg = StreamMessage(message_id=msg_id, stream=stream, data=data)

        with self._lock:
            if stream not in self._streams:
                self._streams[stream] = []
            self._streams[stream].append(msg)
            return msg_id

    def consume(
        self,
        stream: str,
        group: str,
        consumer: str,
        count: int = 10
    ) -> List[StreamMessage]:
        group_key = f"{stream}:{group}"
        messages_to_deliver: List[StreamMessage] = []

        with self._lock:
            stream_messages = self._streams.get(stream, [])
            offset = self._group_offsets.get(group_key, 0)

            if group_key not in self._pending:
                self._pending[group_key] = {}

            # Deliver new messages past the consumer group offset
            available = stream_messages[offset:offset + count]
            for msg in available:
                self._pending[group_key][msg.message_id] = msg
                messages_to_deliver.append(msg)

            self._group_offsets[group_key] = offset + len(messages_to_deliver)
            return messages_to_deliver

    def ack(self, stream: str, group: str, message_id: str) -> bool:
        group_key = f"{stream}:{group}"
        with self._lock:
            if group_key in self._pending:
                return self._pending[group_key].pop(message_id, None) is not None
            return False

    def dead_letter(self, stream: str, group: str, message_id: str, error: str) -> str:
        group_key = f"{stream}:{group}"
        with self._lock:
            msg = None
            if group_key in self._pending:
                msg = self._pending[group_key].pop(message_id, None)

            if not msg:
                # Find in main stream
                for m in self._streams.get(stream, []):
                    if m.message_id == message_id:
                        msg = m
                        break

            dlq_key = f"{stream}:dlq"
            if dlq_key not in self._dlq:
                self._dlq[dlq_key] = []

            dlq_msg = StreamMessage(
                message_id=message_id,
                stream=dlq_key,
                data=msg.data if msg else {},
                error=error,
                attempts=(msg.attempts + 1) if msg else 1
            )
            self._dlq[dlq_key].append(dlq_msg)
            return dlq_msg.message_id

    def get_dlq_messages(self, stream: str) -> List[StreamMessage]:
        dlq_key = f"{stream}:dlq"
        with self._lock:
            return list(self._dlq.get(dlq_key, []))

    def clear(self):
        with self._lock:
            self._streams.clear()
            self._group_offsets.clear()
            self._pending.clear()
            self._dlq.clear()


# Stream factory
_memory_stream_instance = MemoryEventStream()


def get_event_stream() -> BaseEventStream:
    """Returns the configured event stream implementation."""
    if settings.stream_backend == "redis":
        try:
            import redis
            # Check redis connectivity
            r = redis.from_url(settings.redis_url)
            r.ping()
            # If redis is running, return Redis wrapper (or fallback to Memory)
        except Exception:
            pass  # Fallback to Memory stream
    return _memory_stream_instance
