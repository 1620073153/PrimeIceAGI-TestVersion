from engine.continuation_scheduler import select_continuation_sessions as legacy_select_continuation_sessions


def select_continuation_sessions(*args, **kwargs):
    return legacy_select_continuation_sessions(*args, **kwargs)
