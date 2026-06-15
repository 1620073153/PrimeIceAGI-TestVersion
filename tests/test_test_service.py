import backend.services.test_service as test_service


class FakeOrchestrator:
    def __init__(self, config, event_callback):
        self.current_round = 0
        self.event_callback = event_callback

    def run(self):
        self.event_callback("complete", report={"ok": True})
        return {"ok": True}


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


class ImmediateTimer:
    scheduled_delays = []

    def __init__(self, delay, function, args=()):
        self.delay = delay
        self.function = function
        self.args = args
        self.daemon = False
        ImmediateTimer.scheduled_delays.append(delay)

    def start(self):
        self.function(*self.args)


def test_finished_test_schedules_event_bus_cleanup(monkeypatch):
    cleaned_task_ids = []
    ImmediateTimer.scheduled_delays = []

    monkeypatch.setattr(test_service, "RedTeamOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(test_service.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(test_service.threading, "Timer", ImmediateTimer)
    monkeypatch.setattr(test_service, "save_session", lambda *args, **kwargs: None)
    monkeypatch.setattr(test_service._bus, "cleanup", lambda task_id: cleaned_task_ids.append(task_id))

    task_id = test_service.start_test({
        "target_api_url": "http://127.0.0.1/mock",
        "target_api_key": "test-key",
    })

    assert cleaned_task_ids == [task_id]
    assert ImmediateTimer.scheduled_delays == [test_service.EVENT_BUS_CLEANUP_DELAY_SECONDS]
