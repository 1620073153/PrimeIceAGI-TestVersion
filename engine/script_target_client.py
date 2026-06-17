"""
脚本执行器 — 执行 LLM 编译的 Python 脚本，暴露与 TargetClient 相同接口
"""

import json
import time
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from engine.rate_limiter import TokenBucketRateLimiter


class ScriptTargetClient:
    """基于 LLM 编译脚本的待测模型客户端"""

    def __init__(self, config: dict):
        self.config = config
        self.script = config.get("compiled_script", "")
        self.mode = config.get("script_mode", "single")

        # exec 脚本，获取函数引用
        self._namespace = {}
        self._session_store = {}  # orchestrator session_id -> script session dict
        self._compile_script()

    def _compile_script(self):
        """exec 脚本到命名空间，提取 call_target / create_session"""
        import builtins as _builtins

        ALLOWED_MODULES = {"requests", "json", "time", "re"}

        def _restricted_import(name, *args, **kwargs):
            if name not in ALLOWED_MODULES:
                raise ImportError(f"不允许导入模块: {name}")
            return __import__(name, *args, **kwargs)

        safe_globals = {
            "__builtins__": {
                k: getattr(_builtins, k)
                for k in dir(_builtins)
                if not k.startswith("_")
            },
            "requests": requests,
            "json": json,
            "time": time,
            "re": re,
        }
        safe_globals["__builtins__"]["__import__"] = _restricted_import

        try:
            exec(self.script, safe_globals, self._namespace)
        except Exception as e:
            raise RuntimeError(f"脚本编译失败: {e}")

        if "call_target" not in self._namespace:
            raise RuntimeError("脚本缺少 call_target 函数")

        if self.mode == "dual" and "create_session" not in self._namespace:
            raise RuntimeError("双流量包模式脚本缺少 create_session 函数")

    def call_single(self, prompt: str, prompt_id: str = "", extra: dict | None = None) -> dict:
        """单次调用，接口与 TargetClient.call_single 一致"""
        result = {
            "prompt_id": prompt_id,
            "prompt_text": prompt,
            "target_category": (extra or {}).get("target_category", ""),
            "concept": (extra or {}).get("concept", ""),
            "method": (extra or {}).get("method", ""),
            "status": "error",
            "response_text": "",
            "reasoning_text": "",
            "raw_response": None,
            "error": None,
            "latency_ms": 0,
        }

        try:
            call_fn = self._namespace["call_target"]

            if self.mode == "dual":
                session_fn = self._namespace["create_session"]
                session = session_fn()
                raw = call_fn(prompt, session=session)
                result["_script_session"] = session
            else:
                raw = call_fn(prompt)

            if not isinstance(raw, dict):
                result["error"] = f"脚本返回类型错误: 期望 dict, 实际 {type(raw).__name__}"
                return result

            # 标准化输出
            result["response_text"] = raw.get("response_text", "")
            result["reasoning_text"] = raw.get("reasoning_text", "")
            result["status"] = raw.get("status", "success")
            result["error"] = raw.get("error")
            result["latency_ms"] = raw.get("latency_ms", 0)
            result["raw_response"] = raw

        except Exception as e:
            result["error"] = f"脚本执行错误: {str(e)[:300]}"

        return result

    def call_batch(self, prompts: list[dict], max_workers: int = 10,
                   rate_limit: float = 5.0) -> list[dict]:
        """并行调用，接口与 TargetClient.call_batch 一致"""
        limiter = TokenBucketRateLimiter(rate=rate_limit, capacity=max(1, int(rate_limit)))
        results = [None] * len(prompts)

        def _call_one(idx: int, p: dict) -> tuple[int, dict]:
            limiter.acquire(timeout=300)
            return idx, self.call_single(
                prompt=p.get("prompt_text", ""),
                prompt_id=p.get("prompt_id", f"p{idx+1:02d}"),
                extra=p,
            )

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_call_one, i, p) for i, p in enumerate(prompts)]
            for f in as_completed(futures):
                try:
                    idx, res = f.result()
                    results[idx] = res
                except Exception as e:
                    pass

        for i in range(len(results)):
            if results[i] is None:
                results[i] = {
                    "prompt_id": prompts[i].get("prompt_id", f"p{i+1:02d}"),
                    "prompt_text": prompts[i].get("prompt_text", ""),
                    "status": "error",
                    "response_text": "",
                    "error": "未知错误：结果未被填充",
                    "latency_ms": 0,
                }

        return results

    def register_session(self, session_id: str, first_result: dict):
        """orchestrator 创建会话后调用，存储 script session 供续攻复用"""
        script_session = first_result.get("_script_session")
        if script_session:
            self._session_store[session_id] = script_session

    def call_with_history(self, messages: list[dict], session_id: str = "",
                          turn_num: int = 1) -> dict:
        """多轮续攻：双流量包复用 session，单流量包传 history"""
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m["content"]
                break

        result = {
            "prompt_id": f"turn{turn_num}",
            "prompt_text": last_user,
            "status": "error",
            "response_text": "",
            "reasoning_text": "",
            "raw_response": None,
            "error": None,
            "latency_ms": 0,
            "session_id": session_id,
            "turn": turn_num,
            "history_length": len(messages),
        }

        try:
            call_fn = self._namespace["call_target"]

            if self.mode == "dual" and session_id in self._session_store:
                session = self._session_store[session_id]
                raw = call_fn(last_user, session=session, history=messages[:-1])
            else:
                raw = call_fn(last_user, history=messages[:-1])

            if not isinstance(raw, dict):
                result["error"] = f"脚本返回类型错误: 期望 dict, 实际 {type(raw).__name__}"
                return result

            result["response_text"] = raw.get("response_text", "")
            result["reasoning_text"] = raw.get("reasoning_text", "")
            result["status"] = raw.get("status", "success")
            result["error"] = raw.get("error")
            result["latency_ms"] = raw.get("latency_ms", 0)
            result["raw_response"] = raw

        except TypeError:
            # 旧脚本不支持 history 参数，回退到只传 prompt
            try:
                if self.mode == "dual" and session_id in self._session_store:
                    raw = call_fn(last_user, session=self._session_store[session_id])
                else:
                    raw = call_fn(last_user)

                if not isinstance(raw, dict):
                    result["error"] = f"脚本返回类型错误: 期望 dict, 实际 {type(raw).__name__}"
                    return result

                result["response_text"] = raw.get("response_text", "")
                result["reasoning_text"] = raw.get("reasoning_text", "")
                result["status"] = raw.get("status", "success")
                result["error"] = raw.get("error")
                result["latency_ms"] = raw.get("latency_ms", 0)
                result["raw_response"] = raw
            except Exception as e:
                result["error"] = f"脚本执行错误: {str(e)[:300]}"
        except Exception as e:
            result["error"] = f"脚本执行错误: {str(e)[:300]}"

        return result
