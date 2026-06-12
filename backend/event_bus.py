"""
EventBus — 事件广播系统
========================
- 替代 queue.Queue，支持多消费者订阅
- 内部用 threading.Condition + 环形缓冲区
- 每个 subscriber 维护自己的读位置
- 保留最近 200 条事件用于新客户端追赶（历史回放）
"""

import threading
import time
from typing import Generator, Optional


_BUFFER_SIZE = 200  # 每个任务保留最近 200 条事件


class _TaskChannel:
    """单个任务的事件通道，带环形缓冲区"""

    def __init__(self):
        self._buffer: list[dict] = []
        self._write_pos: int = 0  # 累计写入总数（单调递增）
        self._condition = threading.Condition()
        self._closed = False

    @property
    def total_written(self) -> int:
        return self._write_pos

    def publish(self, event: dict):
        """发布一条事件到通道"""
        with self._condition:
            self._buffer.append(event)
            # 超过缓冲区大小则裁剪前面的
            if len(self._buffer) > _BUFFER_SIZE:
                self._buffer = self._buffer[-_BUFFER_SIZE:]
            self._write_pos += 1
            self._condition.notify_all()

    def close(self):
        """关闭通道（任务结束时调用）"""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def subscribe(self, from_pos: int = 0) -> Generator[dict, None, None]:
        """
        订阅事件流。
        from_pos: 从第几条事件开始读（0 = 从头，用于历史回放）
        返回 generator，yield 事件 dict
        """
        # 计算缓冲区中最早可用的位置
        with self._condition:
            buffer_start_pos = self._write_pos - len(self._buffer)
            # 如果请求的位置比缓冲区最早的还早，从缓冲区头开始
            read_pos = max(from_pos, buffer_start_pos)

        while True:
            with self._condition:
                # 等待新事件或关闭
                while read_pos >= self._write_pos and not self._closed:
                    # 每 30 秒超时一次用于发心跳
                    self._condition.wait(timeout=30)
                    if read_pos >= self._write_pos and not self._closed:
                        # 超时发心跳
                        yield {"event": "heartbeat", "timestamp": time.time()}

                if read_pos >= self._write_pos and self._closed:
                    return  # 通道关闭且没有更多事件

                # 读取所有新事件
                buffer_start_pos = self._write_pos - len(self._buffer)
                # 从缓冲区中读出 [read_pos, self._write_pos) 的事件
                buf_offset = read_pos - buffer_start_pos
                end_offset = self._write_pos - buffer_start_pos
                events_to_yield = self._buffer[buf_offset:end_offset]
                read_pos = self._write_pos

            # 在锁外 yield
            for ev in events_to_yield:
                yield ev
                # 如果是终结事件，直接结束
                if ev.get("event") in ("complete", "aborted", "error"):
                    return


class EventBus:
    """全局事件总线 — 单例"""

    _instance: Optional["EventBus"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._channels: dict[str, _TaskChannel] = {}
        self._ch_lock = threading.Lock()

    def _get_or_create_channel(self, task_id: str) -> _TaskChannel:
        with self._ch_lock:
            if task_id not in self._channels:
                self._channels[task_id] = _TaskChannel()
            return self._channels[task_id]

    def publish(self, task_id: str, event: dict):
        """广播事件到指定任务的所有订阅者"""
        channel = self._get_or_create_channel(task_id)
        channel.publish(event)
        # 如果是终结事件，关闭通道
        if event.get("event") in ("complete", "aborted", "error"):
            channel.close()

    def subscribe(self, task_id: str, from_beginning: bool = True) -> Generator[dict, None, None]:
        """
        订阅某任务的事件流。
        from_beginning=True 时从缓冲区最早的事件开始（历史回放）
        """
        channel = self._get_or_create_channel(task_id)
        start_pos = 0 if from_beginning else channel.total_written
        return channel.subscribe(from_pos=start_pos)

    def cleanup(self, task_id: str):
        """清理已结束任务的通道（释放内存）"""
        with self._ch_lock:
            self._channels.pop(task_id, None)
