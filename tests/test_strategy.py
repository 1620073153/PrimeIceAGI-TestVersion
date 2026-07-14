"""策略仲裁器测试 — 验证动态加载和策略决策"""

from engine.strategy_arbitrator import (
    decide_next_strategy,
    _load_categories,
    _load_concepts,
    _load_methods,
)


class TestStrategyLoaders:
    def test_load_categories(self):
        cats = _load_categories()
        assert isinstance(cats, dict)
        assert len(cats) > 0

    def test_load_concepts(self):
        concepts = _load_concepts()
        assert isinstance(concepts, dict)
        assert len(concepts) > 0

    def test_load_methods(self):
        methods = _load_methods()
        assert isinstance(methods, dict)
        assert len(methods) > 0


class TestDecideStrategy:
    def test_first_round_with_no_history(self):
        stats = {"bypassed": 0, "blocked": 0, "partial": 0, "primary_signal": None, "signal_distribution": {}}
        current = {"primary_concept": "认知层次陷阱", "primary_method": "学术讨论包装", "primary_cluster": "A2", "subcategories": []}
        strategy = decide_next_strategy(
            stats=stats,
            current_strategy=current,
            round_num=1,
            covered_categories=[],
        )
        assert "subcategories" in strategy
        assert "primary_concept" in strategy
        assert "primary_method" in strategy

    def test_adapts_on_refusal_signal(self):
        stats = {"bypassed": 0, "blocked": 10, "partial": 0, "primary_signal": "refusal_direct", "signal_distribution": {"refusal_direct": 10}}
        current = {"primary_concept": "认知层次陷阱", "primary_method": "学术讨论包装", "primary_cluster": "A2", "subcategories": ["A2-d", "A2-f"]}
        strategy = decide_next_strategy(
            stats=stats,
            current_strategy=current,
            round_num=2,
            covered_categories=[],
        )
        assert strategy["primary_concept"] != current["primary_concept"] or strategy["primary_method"] != current["primary_method"]

    def test_success_does_not_convert_all_new_attack_slots_to_variants(self):
        stats = {"bypassed": 3, "blocked": 5, "partial": 2, "primary_signal": None, "signal_distribution": {}}
        current = {
            "primary_concept": "认知层次陷阱",
            "primary_method": "学术讨论包装",
            "primary_cluster": "A2",
            "subcategories": ["A2-a", "A2-b", "A2-e"],
            "scan_mode": False,
        }
        successful_prompts = [
            {
                "prompt_id": "p01",
                "prompt_text": "should not be copied",
                "target_category": "A2-a",
                "strategy_tags": ["角色扮演", "authority_framing"],
                "concept": "角色扮演",
                "method": "authority_framing",
            },
            {
                "prompt_id": "p02",
                "prompt_text": "should not be copied either",
                "target_category": "A2-b",
                "strategy_tags": ["indirect_goal", "学术讨论包装"],
                "concept": "indirect_goal",
                "method": "学术讨论包装",
            },
        ]

        strategy = decide_next_strategy(
            stats=stats,
            current_strategy=current,
            round_num=3,
            covered_categories=["A2-a", "A2-b"],
            successful_prompts=successful_prompts,
        )

        assert strategy["variant_mode"] is True
        assert strategy["new_attack_mix"]["success_neighbor_slots"] <= 3
        assert strategy["new_attack_mix"]["fresh_exploration_slots"] >= 5

    def test_successful_templates_are_tag_only_not_full_prompt_copy(self):
        stats = {"bypassed": 1, "blocked": 8, "partial": 1, "primary_signal": None, "signal_distribution": {}}
        current = {
            "primary_concept": "认知层次陷阱",
            "primary_method": "学术讨论包装",
            "primary_cluster": "A2",
            "subcategories": ["A2-d", "A2-f"],
            "scan_mode": False,
        }
        successful_prompts = [
            {
                "prompt_id": "p01",
                "prompt_text": "sensitive full prompt should not be reused",
                "target_category": "A2-d",
                "strategy_tags": ["persona_masking", "narrative_shell"],
                "concept": "persona_masking",
                "method": "narrative_shell",
            }
        ]

        strategy = decide_next_strategy(
            stats=stats,
            current_strategy=current,
            round_num=2,
            covered_categories=["A2-d"],
            successful_prompts=successful_prompts,
        )

        assert strategy["successful_templates"][0]["target_category"] == "A2-d"
        assert strategy["successful_templates"][0]["strategy_tags"] == ["persona_masking", "narrative_shell"]
        assert "prompt_text" not in strategy["successful_templates"][0]
