"""
统一 LLM 调用客户端
集成限流、429 退避、超时控制、自动重试
供 prompt_generator / deepener / system_prompt_inferrer 共用
"""

import requests
from typing import Optional

from engine.rate_limiter import AdaptiveRateLimiter


class LLMClient:
    """
    OpenAI 兼容格式的 LLM 调用客户端

    功能:
    - 单轮 / 多轮对话调用
    - 内置 AdaptiveRateLimiter（默认 1 req/s）
    - 收到 429 后自动退避 5 分钟再重试
    - 超时控制（默认 90s）
    - 重试机制（最多 2 次，仅对超时和 5xx 重试）
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        rate_limit: float = 1.0,
        timeout: float = 90.0,
        max_retries: int = 2,
        backoff_429: float = 300.0,
    ):
        """
        api_url: API base URL (不含 /chat/completions)
        api_key: Bearer token
        model: 模型名
        rate_limit: QPS 限制（默认 1.0）
        timeout: 请求超时秒数（默认 90）
        max_retries: 最大重试次数（默认 2，仅对超时和 5xx）
        backoff_429: 收到 429 后暂停秒数（默认 300 = 5分钟）
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

        self._limiter = AdaptiveRateLimiter(
            initial_rate=rate_limit,
            capacity=max(1, int(rate_limit)),
            backoff_seconds=backoff_429,
        )

    @property
    def current_rate(self) -> float:
        """当前实际速率"""
        return self._limiter.current_rate

    def call(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.9,
        max_tokens: int = 4096,
    ) -> str:
        """
        单轮调用（system + user）

        返回 assistant 的回复文本。
        失败时抛出异常。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return self.call_messages(messages, temperature=temperature, max_tokens=max_tokens)

    def call_messages(
        self,
        messages: list[dict],
        temperature: float = 0.9,
        max_tokens: int = 4096,
    ) -> str:
        """
        多轮调用（传入完整 messages 列表）

        返回 assistant 的回复文本。
        失败时抛出异常。
        """
        url = self.api_url + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "enable_thinking": False,
        }

        last_error: Optional[Exception] = None

        for attempt in range(1 + self.max_retries):
            # 限流：等待令牌
            acquired = self._limiter.acquire(timeout=self.timeout + 300)
            if not acquired:
                raise TimeoutError("限流器等待超时，可能处于 429 退避期")

            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout,
                )

                # 429 处理：报告并重试
                if resp.status_code == 429:
                    self._limiter.report_429()
                    last_error = requests.exceptions.HTTPError(
                        f"429 Too Many Requests: {resp.text[:200]}"
                    )
                    # 429 总是重试（不计入 max_retries 的常规重试）
                    continue

                # 5xx 处理：可重试
                if resp.status_code >= 500:
                    self._limiter.report_error()
                    last_error = requests.exceptions.HTTPError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    if attempt < self.max_retries:
                        continue
                    raise last_error

                # 其他 4xx：不重试，直接报错
                if resp.status_code >= 400:
                    raise requests.exceptions.HTTPError(
                        f"HTTP {resp.status_code}: {resp.text[:300]}"
                    )

                # 成功
                self._limiter.report_success()
                data = resp.json()
                content = data["choices"][0]["message"].get("content")
                if not content:
                    content = data["choices"][0]["message"].get("reasoning_content", "")
                if not content:
                    raise ValueError("API 返回空结果: content 和 reasoning_content 均为空")
                return content

            except requests.exceptions.Timeout:
                self._limiter.report_error()
                last_error = requests.exceptions.Timeout(
                    f"请求超时 ({self.timeout}s)"
                )
                if attempt < self.max_retries:
                    continue
                raise last_error

            except requests.exceptions.ConnectionError as e:
                # 连接重置/中断：暂时性错误，可重试
                self._limiter.report_error()
                last_error = e
                if attempt < self.max_retries:
                    import time
                    time.sleep(2 * (attempt + 1))
                    continue
                raise

            except requests.exceptions.HTTPError:
                raise

            except Exception as e:
                self._limiter.report_error()
                last_error = e
                if attempt < self.max_retries:
                    continue
                raise

        # 所有重试耗尽
        if last_error:
            raise last_error
        raise RuntimeError("LLM 调用失败，重试耗尽")
