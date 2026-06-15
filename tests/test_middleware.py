from flask import Flask

import backend.middleware as middleware


class FakeTimer:
    started_count = 0

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.daemon = False

    def start(self):
        FakeTimer.started_count += 1


def test_rate_limiter_cleanup_timer_starts_only_once(monkeypatch):
    FakeTimer.started_count = 0
    monkeypatch.setattr(middleware.threading, "Timer", FakeTimer)
    monkeypatch.setattr(middleware, "_cleanup_started", False, raising=False)

    middleware.init_security(Flask("first"))
    middleware.init_security(Flask("second"))
    middleware.init_security(Flask("third"))

    assert FakeTimer.started_count == 1
