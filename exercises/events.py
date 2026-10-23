from datetime import datetime
from json import loads
from typing import Callable, Optional


class Event:
    """
    topic, timestamp, data payload
    """

    topic: str = ""
    timestamp: Optional[float] = None
    payload: dict = {}

    def __init__(
        self,
        topic: str,
        payload: str,
        timestamp: Optional[float] = None,
    ):
        self.topic = topic
        if timestamp:
            self.timestamp = timestamp
        else:
            self.timestamp = datetime.now().timestamp()
        self.payload = loads(payload)


# class EventStream
class EventStream:
    """
    method1: register callbacks for topic

    method2: publish events to topic

    should handle multiple subscribers per a topic
    """

    def __init__(self):
        # Dictionary: topic -> list of callbacks
        self.subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, topic: str, callback: Callable):
        """
        subscribe to a topic
        """
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)

    def publish(self, e: Event):
        """
        publish event to topic
        """
        # a pitfall here is that this is syncronous, and there is a bit of a hitch to notify subscribers
        # another option would be to run a thread in the background
        # Thread(target=callback, args=(e,), daemon=True).start()
        if e.topic in self.subscribers:
            for callback in self.subscribers[e.topic]:
                callback(e)


class Producer:
    """
    Produces events and sends them to event stream
    """

    def __init__(self, s: EventStream, name: str = "Producer"):
        self.stream = s
        self.name = name

    def send(self, topic: str, data: str) -> None:
        e = Event(topic, data)
        self.stream.publish(e)


class Consumer:
    """
    Consume events from a topic
    """

    def __init__(self, s: EventStream, name: str, topics: list[str]) -> None:
        self.stream = s
        self.name = name
        self.topics = topics
        self.processed_count = 0

        for topic in topics:
            self.stream.subscribe(topic, self.handle_event)

    def handle_event(self, e: Event) -> None:
        self.process(e)
        self.processed_count += 1

    def process(self, e: Event) -> None:
        """
        do something
        """
        pass


def process_order(e: Event):
    """
    process order
    """
    print(f"Processing order: {e.payload}")


def log_event(e: Event):
    """
    log the event
    """
    print(f"INFO: {e.topic}, {e.timestamp}, {e.payload}")


def trial_and_error(e: Event):
    """
    do something
    """
    print(f"This callback was invoked, {e.payload['amount'] * e.payload['id']}")


class OrderConsumer(Consumer):
    def process(self, e: Event):
        if e.topic == "orders":
            order_id = e.payload.get("id")
            amount = e.payload.get("amount")
            print(f" -> Processing Order #{order_id} for ${amount}")


class AnalyticsConsumer(Consumer):
    """Consumer that aggregates metrics"""

    def __init__(self, stream: EventStream, name: str, topics: list[str]):
        super().__init__(stream, name, topics)
        self.total_amount = 0

    def process(self, e: Event):
        if e.topic == "orders" and "amount" in e.payload:
            self.total_amount += e.payload["amount"]
            print(f" -> Total revenue: ${self.total_amount}")
        elif e.topic == "payments":
            status = e.payload.get("status")
            order_id = e.payload.get("order_id")
            print(f"  -> [Analytics] Payment for order #{order_id}: {status}")


# Create event stream
stream = EventStream()

# Register subscribers
# stream.subscribe("orders", process_order)
stream.subscribe("orders", log_event)
stream.subscribe("orders", trial_and_error)

# Publish events
stream.publish(Event("orders", payload='{"id": 1, "amount": 100}'))

# Create producers
order_producer = Producer(stream, name="OrderService")
payment_producer = Producer(stream, name="PaymentService")

# Create consumers
order_processor = OrderConsumer(
    stream, name="OrderProcessor", topics=["orders"]
)
analytics = AnalyticsConsumer(
    stream, name="Analytics", topics=["orders", "payments"]
)
logger = Consumer(stream, name="Logger", topics=["orders", "payments"])

# Simulate event flow
print("\n--- Simulating Order Flow ---\n")
order_producer.send("orders", '{"id": 1, "amount": 100, "item": "Widget"}')
order_producer.send("orders", '{"id": 2, "amount": 250, "item": "Gadget"}')

print("\n--- Simulating Payment Flow ---\n")
payment_producer.send("payments", '{"order_id": 1, "status": "completed"}')
payment_producer.send("payments", '{"order_id": 2, "status": "pending"}')

print("\n--- Stats ---")
print(f"OrderProcessor handled: {order_processor.processed_count} events")
print(f"Analytics handled: {analytics.processed_count} events")
