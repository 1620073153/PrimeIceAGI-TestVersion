"""Input validation functions."""


class ValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_test_config(config: dict) -> dict:
    required = ["agent_api_url", "agent_api_key", "target_api_url", "target_api_key"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        raise ValidationError(f"缺少必填参数: {', '.join(missing)}")

    if config.get("template_name") == "custom":
        if not config.get("headers"):
            raise ValidationError("自定义模板模式下需要填写请求 Headers")
        if not config.get("body"):
            raise ValidationError("自定义模板模式下需要填写请求 Body")

    config.setdefault("agent_model", "deepseek-chat")
    config.setdefault("target_model", "deepseek-chat")
    config.setdefault("max_rounds", 5)
    config.setdefault("cooldown_no_new", 2)
    config.setdefault("template_name", "openai_compatible")
    return config


def validate_kb_entry(kb_id: str, entry: dict) -> dict:
    if kb_id == "kb5":
        raise ValidationError("KB5 由 Agent3 自动填充，不可手动编辑")
    if kb_id not in ("kb1", "kb2", "kb3", "kb4"):
        raise ValidationError("无效的知识库 ID")
    if kb_id in ("kb1", "kb2", "kb3") and not entry.get("key"):
        raise ValidationError("缺少 key 字段")
    return entry
