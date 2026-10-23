from threading import Thread


# basic callback pattern
def process_data(data, callback):
    result = data + 2
    callback(result)


def print_result(val):
    print(f"Result: {val}")


process_data(6, print_result)


# observer pattern
class Subject:
    def __init__(self):
        self.callbacks = []

    def register(self, callback):
        self.callbacks.append(callback)

    def notify(self, data):
        for callback in self.callbacks:
            callback(data)


s = Subject()
s.register(lambda x: print(f"Callback 1: {x}"))
s.register(lambda x: print(f"Callback 2: {x * 2}"))
s.notify(22)
s.notify(54)


# callback with state
def counter_callback():
    count = 0

    def callback(val):
        nonlocal count
        count += 1
        print(f"Call #{count}: {val}")

    return callback


counter = counter_callback()
counter("first")
counter("second")


# event exercise
class EventBus:
    def __init__(self):
        self.listeners = {}

    def on(self, event_name, callback):
        # Register callback for event
        if event_name in self.listeners:
            self.listeners[event_name].append(callback)
        else:
            self.listeners[event_name] = [callback]

    def emit(self, event_name, data):
        threads = []

        # Call all callbacks for this event
        if event_name in self.listeners:
            for callback in self.listeners[event_name]:
                # callback(data)
                Thread(target=callback, args=(data,)).start()
        #         t.start()
        #         threads.append(t)

        # for t in threads:
        #     t.join()


# Test it
bus = EventBus()
bus.on("user_login", lambda user: print(f"Welcome {user}"))
bus.on("user_login", lambda user: print(f"Logging activity for {user}"))
bus.emit("user_login", "Alice")
