"""KB 数据层测试 — 验证加载、保存、原子写入"""

import json
import os
import tempfile
from unittest.mock import patch

from data.kb_store import load_kb, save_kb, ensure_seed_files, get_data_dir


class TestLoadKb:
    def test_load_kb1_returns_categories(self):
        data = load_kb("kb1")
        assert "categories" in data
        assert len(data["categories"]) > 0

    def test_load_kb2_returns_concepts(self):
        data = load_kb("kb2")
        assert "concepts" in data

    def test_load_kb3_returns_methods(self):
        data = load_kb("kb3")
        assert "methods" in data
        assert "signal_strategy_map" in data

    def test_load_kb4_returns_templates(self):
        data = load_kb("kb4")
        assert "templates" in data

    def test_load_kb5_returns_inferences(self):
        data = load_kb("kb5")
        assert "inferences" in data

    def test_load_invalid_kb_returns_empty(self):
        data = load_kb("kb_nonexistent")
        assert data == {}

    def test_load_corrupted_file_falls_back(self, tmp_path):
        corrupted = tmp_path / "kb1.json"
        corrupted.write_text("{invalid json!!", encoding="utf-8")
        with patch("data.kb_store.get_data_dir", return_value=str(tmp_path)):
            data = load_kb("kb1")
        assert "categories" in data


class TestSaveKb:
    def test_save_and_reload(self, tmp_path):
        with patch("data.kb_store.get_data_dir", return_value=str(tmp_path)):
            test_data = {"templates": {"t1": {"name": "test", "template_text": "hello"}}}
            result = save_kb("kb4", test_data)
            assert result is True
            loaded = load_kb("kb4")
            assert loaded["templates"]["t1"]["name"] == "test"

    def test_save_kb5_blocked(self):
        result = save_kb("kb5", {"inferences": []})
        assert result is False


class TestEnsureSeedFiles:
    def test_creates_all_files(self, tmp_path):
        with patch("data.kb_store.get_data_dir", return_value=str(tmp_path)):
            ensure_seed_files()
        expected = ["kb1_standards.json", "kb2_concepts.json", "kb3_methods.json",
                    "kb4_injection_templates.json", "kb5_inferred_boundaries.json"]
        for f in expected:
            assert (tmp_path / f).exists(), f"Missing {f}"

    def test_does_not_overwrite_existing(self, tmp_path):
        custom = {"templates": {"custom": True}}
        kb4_path = tmp_path / "kb4_injection_templates.json"
        kb4_path.write_text(json.dumps(custom), encoding="utf-8")
        with patch("data.kb_store.get_data_dir", return_value=str(tmp_path)):
            ensure_seed_files()
        loaded = json.loads(kb4_path.read_text(encoding="utf-8"))
        assert loaded["templates"]["custom"] is True
