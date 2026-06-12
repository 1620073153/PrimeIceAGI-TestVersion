"""
限流器模块 — 令牌桶 + 自适应限流
线程安全，用于控制 LLM 调用和目标模型调用频率
"""

import time
import threading


class TokenBucketRateLimiter:
    """
    令牌桶限流器

    - 以固定速率向桶中添加令牌
    - 每次请求消耗一个令牌
    - 桶满时多余令牌丢弃（允许小规模突发）
    """

    def __init__(self, rate: float = 1.0, capacity: int = 1):
        """
        rate: 每秒生成的令牌数 (即允许的 QPS)
        capacity: 桶容量（允许的突发请求数）
        """
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    @property
    def rate(self) -> float:
        return self._rate

    @rate.setter
    def rate(self, value: float):
        with self._lock:
            self._refill()
            self._rate = max(0.01, value)

    def _refill(self):
        """补充令牌（需在锁内调用）"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    def acquire(self, timeout: float = 300.0) -> bool:
        """
        获取一个令牌，阻塞直到可用或超时

        timeout: 最大等待时间（秒）
        返回: True 表示成功获取，False 表示超时
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                # 计算需要等待多久才能有一个令牌
                wait_time = (1.0 - self._tokens) / self._rate

            # 检查是否会超时
            if time.monotonic() + wait_time > deadline:
                return False

            time.sleep(min(wait_time, 0.1))

    def try_acquire(self) -> bool:
        """非阻塞尝试获取令牌"""
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


class AdaptiveRateLimiter:
    """
    自适应限流器 — 根据 429 响应动态调整速率

    行为:
    - 收到 429 时：立即暂停指定时间（默认 5 分钟），然后将速率降低 50%
    - 连续成功时：逐步恢复速率（每 10 次成功恢复 10%，不超过初始速率）
    - 线程安全
    """

    def __init__(self, initial_rate: float = 1.0, capacity: int = 1,
                 backoff_seconds: float = 300.0):
        """
        initial_rate: 初始 QPS
        capacity: 令牌桶容量
        backoff_seconds: 收到 429 后暂停的秒数（默认 300 = 5分钟）
        """
        self._initial_rate = initial_rate
        self._backoff_seconds = backoff_seconds
        self._bucket = TokenBucketRateLimiter(rate=initial_rate, capacity=capacity)
        self._lock = threading.Lock()
        self._consecutive_success = 0
        self._paused_until = 0.0  # monotonic timestamp

    @property
    def current_rate(self) -> float:
        return self._bucket.rate

    def acquire(self, timeout: float = 600.0) -> bool:
        """
        获取令牌（阻塞）

        会先检查是否在暂停期内，如果是则等待暂停结束后再获取令牌。
        """
        # 检查是否在暂停期
        with self._lock:
            paused_until = self._paused_until

        if paused_until > 0:
            now = time.monotonic()
            if now < paused_until:
                wait = paused_until - now
                if wait > timeout:
                    return False
                time.sleep(wait)

        return self._bucket.acquire(timeout=timeout)

    def report_success(self):
        """报告一次成功请求，用于逐步恢复速率"""
        with self._lock:
            self._consecutive_success += 1
            if self._consecutive_success >= 10:
                self._consecutive_success = 0
                new_rate = min(self._initial_rate, self._bucket.rate * 1.1)
                self._bucket.rate = new_rate

    def report_429(self):
        """
        报告收到 429，触发退避

        - 暂停 backoff_seconds
        - 速率降低 50%
        """
        with self._lock:
            self._paused_until = time.monotonic() + self._backoff_seconds
            self._bucket.rate = max(0.05, self._bucket.rate * 0.5)
            self._consecutive_success = 0

    def report_error(self):
        """报告非 429 错误（不触发长暂停，但重置连续成功计数）"""
        with self._lock:
            self._consecutive_success = 0
