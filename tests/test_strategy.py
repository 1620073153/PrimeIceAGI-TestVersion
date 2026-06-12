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
        current = {"primary_concept": "cognitive_hierarchy_trap", "primary_method": "academic_framing", "primary_cluster": "A", "subcategories": []}
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
        current = {"primary_concept": "cognitive_hierarchy_trap", "primary_method": "academic_framing", "primary_cluster": "A", "subcategories": ["A-1", "A-2"]}
        strategy = decide_next_strategy(
            stats=stats,
            current_strategy=current,
            round_num=2,
            covered_categories=[],
        )
        assert strategy["primary_concept"] != current["primary_concept"] or strategy["primary_method"] != current["primary_method"]
