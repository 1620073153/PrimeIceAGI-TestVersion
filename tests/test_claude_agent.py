"""Claude Agent 模块测试 — 验证消息构造和解析逻辑"""

from engine.claude_agent import (
    _build_prompt_skill_message,
    _build_continuation_message,
    _parse_prompt_list,
    _parse_freeform_prompts,
    _parse_continuations,
    _preview_text,
)


class TestBuildMessage:
    def test_basic_message_structure(self):
        strategy = {
            "subcategories": ["A-1", "A-2"],
            "primary_concept": "角色扮演",
            "primary_method": "学术伪装",
        }
        msg = _build_prompt_skill_message(round_num=1, strategy=strategy)
        assert "模式A" in msg
        assert "A-1" in msg
        assert "角色扮演" in msg
        assert "JSON数组" in msg

    def test_kb5_injection(self):
        strategy = {"subcategories": ["B-1"], "primary_concept": "", "primary_method": ""}
        msg = _build_prompt_skill_message(
            round_num=2, strategy=strategy, kb5_summary="模型对政治话题极度敏感"
        )
        assert "边界情报" in msg
        assert "政治话题" in msg

    def test_history_feedback_included(self):
        strategy = {"subcategories": ["C-1"], "primary_concept": "", "primary_method": ""}
        msg = _build_prompt_skill_message(
            round_num=3, strategy=strategy, history_feedback="上轮全部被拦截"
        )
        assert "上轮反馈" in msg
        assert "被拦截" in msg

    def test_prompt_skill_message_includes_mix_constraints_for_new_attacks(self):
        strategy = {
            "subcategories": ["B-3", "C-1", "D-2", "E-1"],
            "primary_concept": "cognitive_hierarchy_trap",
            "primary_method": "academic_framing",
            "new_attack_mix": {
                "total_slots": 10,
                "success_neighbor_slots": 3,
                "cross_cluster_slots": 2,
                "fresh_exploration_slots": 5,
            },
            "successful_templates": [
                {"target_category": "B-1", "strategy_tags": ["role_play", "authority_framing"]}
            ],
            "neighbor_subcategories": ["B-3", "B-4"],
            "cross_cluster_subcategories": ["C-1", "D-2"],
            "fresh_subcategories": ["E-1", "F-2", "A-3"],
        }

        message = _build_prompt_skill_message(
            round_num=3,
            strategy=strategy,
            kb5_summary="intel",
            history_feedback="feedback",
            successful_prompts=strategy["successful_templates"],
        )

        assert "最多3条" in message
        assert "至少5条必须来自全新探索" in message
        assert "不得续写已有对话" in message
        assert "只参考手法标签，不复用历史提示词原文" in message


class TestParsePromptList:
    def test_parse_json_array(self):
        raw = '[{"prompt_id":"p01","prompt_text":"test prompt","target_category":"A-1","strategy_tags":["tag1"]}]'
        result = _parse_prompt_list(raw)
        assert len(result) == 1
        assert result[0]["prompt_id"] == "p01"

    def test_parse_code_block(self):
        raw = '```json\n[{"prompt_id":"p01","prompt_text":"hello","target_category":"B-1","strategy_tags":[]}]\n```'
        result = _parse_prompt_list(raw)
        assert len(result) == 1

    def test_parse_empty_returns_empty(self):
        assert _parse_prompt_list("no json here") == []

    def test_parse_embedded_array(self):
        raw = 'Some text before\n[{"prompt_id":"p01","prompt_text":"embedded","target_category":"A-1","strategy_tags":[]}]\nSome text after'
        result = _parse_prompt_list(raw)
        assert len(result) == 1


class TestParseContinuations:
    def test_parse_matching_sessions(self):
        raw = '[{"session_id":"s1","prompt_text":"continue attacking this way"}]'
        sessions = [{"session_id": "s1", "target_category": "A-1"}]
        result = _parse_continuations(raw, sessions)
        assert len(result) == 1
        assert result[0]["type"] == "continue"
        assert result[0]["session_id"] == "s1"

    def test_fallback_sequential_assignment(self):
        raw = '[{"prompt_text":"续攻内容一号，详细的攻击文本超过二十个字符的"}]'
        sessions = [{"session_id": "s1", "target_category": "B-2"}]
        result = _parse_continuations(raw, sessions)
        assert len(result) == 1
        assert result[0]["session_id"] == "s1"

    def test_short_prompt_filtered(self):
        raw = '[{"session_id":"s1","prompt_text":"too short"}]'
        sessions = [{"session_id": "s1", "target_category": "A-1"}]
        result = _parse_continuations(raw, sessions)
        assert len(result) == 0


class TestDiagnostics:
    def test_preview_text_compacts_and_truncates_raw_output(self):
        raw = "第一行\n\n第二行\t" + "x" * 30
        preview = _preview_text(raw, limit=12)
        assert preview.startswith("第一行 第二行")
        assert "\n" not in preview
        assert preview.endswith("...<truncated>")


class TestBuildContinuationMessage:
    def test_message_uses_selected_session_wording_and_reason(self):
        message = _build_continuation_message(
            [
                {
                    "session_id": "s1",
                    "turn_num": 2,
                    "target_category": "A-1",
                    "selection_reason": "fresh_success",
                    "state_summary": {
                        "session_id": "s1",
                        "target_category": "A-1",
                        "selection_reason": "fresh_success",
                    },
                    "recent_context_fragments": [
                        {"role": "assistant", "content": "回应"},
                        {"role": "user", "content": "继续"},
                    ],
                    "messages": [
                        {"role": "user", "content": "旧消息1"},
                        {"role": "assistant", "content": "旧消息2"},
                    ],
                }
            ]
        )

        assert "入选会话" in message
        assert "fresh_success" in message
        assert "共1个入选会话" in message
        assert "[assistant]: 回应" in message
        assert "[user]: 继续" in message
        assert "旧消息1" not in message
