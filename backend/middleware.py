"""
安全中间件
==========
- 可选 Token 认证（环境变量 PRIMEICE_TOKEN 控制）
- 基于 IP 的请求频率限制（60 req/min）
"""

import os
import time
import threading
from functools import wraps
from flask import Flask, request, jsonify


class _RateLimiter:
    """基于滑动窗口的 IP 频率限制器"""

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            timestamps = self._requests.get(ip, [])
            # 清除过期记录
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self._max:
                self._requests[ip] = timestamps
                return False
            timestamps.append(now)
            self._requests[ip] = timestamps
            return True

    def cleanup(self):
        """定期清理过期 IP 记录"""
        now = time.time()
        cutoff = now - self._window * 2
        with self._lock:
            expired_ips = [
                ip for ip, ts in self._requests.items()
                if not ts or ts[-1] < cutoff
            ]
            for ip in expired_ips:
                del self._requests[ip]


_rate_limiter = _RateLimiter(max_requests=60, window_seconds=60)
_cleanup_started = False
_cleanup_start_lock = threading.Lock()


def _start_rate_limiter_cleanup():
    """每 5 分钟清理一次过期记录，且每个进程只启动一次。"""
    global _cleanup_started

    with _cleanup_start_lock:
        if _cleanup_started:
            return
        _cleanup_started = True

    def loop():
        _rate_limiter.cleanup()
        timer = threading.Timer(300, loop)
        timer.daemon = True
        timer.start()

    timer = threading.Timer(300, loop)
    timer.daemon = True
    timer.start()


def init_security(app: Flask):
    """初始化安全中间件到 Flask app"""
    token = os.environ.get("PRIMEICE_TOKEN", "").strip()
    _start_rate_limiter_cleanup()

    @app.before_request
    def _security_check():
        # 跳过静态文件和页面路由
        if request.path.startswith("/static") or request.path == "/":
            return None

        # Token 认证（仅在环境变量设置时启用）
        if token:
            auth_header = request.headers.get("Authorization", "")
            req_token = ""
            if auth_header.startswith("Bearer "):
                req_token = auth_header[7:].strip()
            elif request.args.get("token"):
                req_token = request.args.get("token", "").strip()

            if req_token != token:
                return jsonify({"error": "认证失败: 无效的 Token"}), 401

        # 频率限制
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if client_ip:
            client_ip = client_ip.split(",")[0].strip()
        if not _rate_limiter.is_allowed(client_ip):
            return jsonify({"error": "请求过于频繁，请稍后再试"}), 429

        return None
