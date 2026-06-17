"""Input validation functions."""


class ValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def validate_test_config(config: dict) -> dict:
    # 脚本模式：有 compiled_script 就跳过传统校验
    if config.get("template_name") == "custom" and config.get("compiled_script"):
        config.setdefault("target_api_url", "script://compiled")
        config.setdefault("max_rounds", 5)
        config.setdefault("cooldown_no_new", 2)
        return config

    if not config.get("target_api_url"):
        raise ValidationError("请填写待测模型的 API 地址")

    # 非自定义模板需要 API Key（标准 OpenAI/Anthropic 格式必须有 key）
    if config.get("template_name") != "custom" and not config.get("target_api_key"):
        raise ValidationError("请填写待测模型的 API Key")

    if config.get("template_name") == "custom":
        if not config.get("body") and not config.get("compiled_script"):
            raise ValidationError("自定义模板模式下需要填写请求 Body 或编译脚本")

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
