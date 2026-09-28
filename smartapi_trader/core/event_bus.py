import asyncio
from typing import Dict, List, Callable, Awaitable, Any, Union
from smartapi_trader.core.events import BaseEvent, EventType
from smartapi_trader.utils.logger import logger

SubscriberCallback = Callable[[BaseEvent], Awaitable[None]]

class EventBus:
    """
    High-performance asynchronous pub/sub event bus.
    Facilitates decoupled communication between streaming feeds, candle aggregators,
    strategy evaluators, risk managers, execution routers, and UI telemetry.
    """
    def __init__(self):
        self._subscribers: Dict[Union[EventType, str], List[SubscriberCallback]] = {}
        self._running: bool = True
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._dispatch_task: asyncio.Task = None

    def start(self):
        """Starts the background event dispatch loop."""
        if self._dispatch_task is None or self._dispatch_task.done():
            self._running = True
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = None
            self._dispatch_task = asyncio.create_task(self._process_queue())
            logger.info("[EVENT_BUS] Event bus dispatch loop started.")

    async def stop(self):
        """Stops the event bus and flushes queued events."""
        self._running = False
        if self._dispatch_task:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None
        logger.info("[EVENT_BUS] Event bus stopped.")

    def subscribe(self, event_type: Union[EventType, str], callback: SubscriberCallback):
        """Registers a callback for a specific event type or wildcard '*'."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)
            logger.debug(f"[EVENT_BUS] Subscribed callback {callback.__name__} to {event_type}")

    def unsubscribe(self, event_type: Union[EventType, str], callback: SubscriberCallback):
        """Removes a registered callback."""
        if event_type in self._subscribers and callback in self._subscribers[event_type]:
            self._subscribers[event_type].remove(callback)

    async def publish(self, event: BaseEvent):
        """Publishes an event to the processing queue."""
        if not self._running:
            return
        await self._event_queue.put(event)

    def publish_nowait(self, event: BaseEvent):
        """Thread-safe synchronous non-blocking enqueue helper."""
        if not self._running:
            return
        if hasattr(self, "_loop") and self._loop and self._loop.is_running():
            try:
                if asyncio.get_running_loop() is self._loop:
                    self._event_queue.put_nowait(event)
                    return
            except RuntimeError:
                pass
            self._loop.call_soon_threadsafe(self._event_queue.put_nowait, event)
        else:
            self._event_queue.put_nowait(event)

    async def _process_queue(self):
        """Continuous event consumption and parallel subscriber dispatch."""
        while self._running:
            try:
                event: BaseEvent = await self._event_queue.get()
                await self._dispatch(event)
                self._event_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EVENT_BUS] Unexpected exception in event queue processing: {e}")

    async def _dispatch(self, event: BaseEvent):
        """Dispatches event to exact type listeners and wildcard listeners."""
        handlers = []
        if event.event_type in self._subscribers:
            handlers.extend(self._subscribers[event.event_type])
        if "*" in self._subscribers:
            handlers.extend(self._subscribers["*"])

        if not handlers:
            return

        tasks = []
        for handler in handlers:
            tasks.append(self._invoke_handler(handler, event))
        
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _invoke_handler(self, handler: SubscriberCallback, event: BaseEvent):
        """Invokes a single handler with error isolation."""
        try:
            await handler(event)
        except Exception as e:
            logger.error(f"[EVENT_BUS] Error executing handler {handler.__name__} for {event.event_type}: {e}")
