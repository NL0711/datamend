"""The MQTT transport seam of the ESP32 source, and the real transport over ``paho-mqtt``.

NOT VERIFIED ON A REAL DEVICE OR BROKER: the owner has no ESP32 hardware, so ``PahoTransport`` has never connected to anything. The source is
tested against a fake transport (tests/test_stream_esp32.py). ``paho-mqtt`` is imported only when a connection is made, so the module and the
whole app import without it; without it the source says so when asked to connect.

Handlers are called on the asyncio event loop thread (PahoTransport hands paho's thread callbacks over with ``call_soon_threadsafe``).
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional, Protocol, Sequence

MessageHandler = Callable[[str, bytes], None]
ConnectionHandler = Callable[[bool, Optional[str]], None]       # (connected, reason when not)


class MqttTransport(Protocol):
    def set_handlers(self, on_message: MessageHandler, on_connection: ConnectionHandler) -> None: ...
    async def connect(self, host: str, port: int, username: str, password: str, tls: bool) -> None:
        """Connect and return once the broker accepted the connection, or raise."""
    async def subscribe(self, topic_filters: Sequence[str]) -> None: ...
    async def disconnect(self) -> None: ...


class MqttUnavailable(RuntimeError):
    """The MQTT client library is not installed."""


class PahoTransport:
    """paho-mqtt 2.x over its own network thread. NOT verified against a real broker."""

    def __init__(self, connect_timeout_s: float = 10.0) -> None:
        self._timeout = connect_timeout_s
        self._client = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._on_message: Optional[MessageHandler] = None
        self._on_connection: Optional[ConnectionHandler] = None
        self._filters: Sequence[str] = ()
        self._connected: Optional[asyncio.Future] = None

    def set_handlers(self, on_message: MessageHandler, on_connection: ConnectionHandler) -> None:
        self._on_message, self._on_connection = on_message, on_connection

    def _to_loop(self, fn, *args) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(fn, *args)

    async def connect(self, host: str, port: int, username: str, password: str, tls: bool) -> None:
        try:
            import paho.mqtt.client as mqtt          # lazy: the app runs without paho
        except ImportError as exc:
            raise MqttUnavailable("the paho-mqtt package is not installed (pip install 'paho-mqtt>=2.1,<3')") from exc
        self._loop = asyncio.get_running_loop()
        self._connected = self._loop.create_future()
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            client.username_pw_set(username, password or None)
        if tls:
            client.tls_set()

        def on_connect(c, userdata, flags, reason_code, properties=None):
            ok = not reason_code.is_failure
            if ok and self._filters:
                c.subscribe([(f, 0) for f in self._filters])          # also after an automatic reconnect
            self._to_loop(self._connect_result, ok, None if ok else str(reason_code))

        def on_disconnect(c, userdata, flags, reason_code, properties=None):
            self._to_loop(self._lost, str(reason_code))

        def on_message(c, userdata, msg):
            self._to_loop(self._deliver, msg.topic, bytes(msg.payload))

        client.on_connect, client.on_disconnect, client.on_message = on_connect, on_disconnect, on_message
        self._client = client
        client.connect_async(host, port, keepalive=60)
        client.loop_start()
        try:
            await asyncio.wait_for(self._connected, self._timeout)
        except Exception:
            await self.disconnect()
            raise

    def _connect_result(self, ok: bool, reason: Optional[str]) -> None:
        if self._connected is not None and not self._connected.done():
            if ok:
                self._connected.set_result(True)
            else:
                self._connected.set_exception(ConnectionError(f"the broker refused the connection: {reason}"))
        if self._on_connection:
            self._on_connection(ok, reason)

    def _lost(self, reason: str) -> None:
        if self._on_connection:
            self._on_connection(False, reason)

    def _deliver(self, topic: str, payload: bytes) -> None:
        if self._on_message:
            self._on_message(topic, payload)

    async def subscribe(self, topic_filters: Sequence[str]) -> None:
        self._filters = tuple(topic_filters)
        if self._client is not None:
            self._client.subscribe([(f, 0) for f in self._filters])

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                client.disconnect()
            finally:
                client.loop_stop()
