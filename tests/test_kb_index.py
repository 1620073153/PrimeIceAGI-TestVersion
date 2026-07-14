from engine.knowledge.kb_index import build_runtime_indexes


def test_build_runtime_indexes_exposes_category_template_and_success_maps(tmp_path):
    kb_root = tmp_path / "kb_data"
    derived_root = kb_root / "derived"
    derived_root.mkdir(parents=True)

    (kb_root / "kb1.json").write_text('{"categories":{"A2":{"subcategories":{"A2-a":{},"A2-b":{}}},"A1":{"subcategories":{"A1-f":{}}}}}', encoding="utf-8")
    (kb_root / "kb2.json").write_text('{"concepts":{"角色扮演":{}}}', encoding="utf-8")
    (kb_root / "kb3.json").write_text('{"methods":{"学术讨论包装":{}},"signal_strategy_map":{}}', encoding="utf-8")
    (kb_root / "kb4.json").write_text('{"templates":{"t1":{"category":"A2-a","tags":["角色扮演"],"template_text":"template body"}}}', encoding="utf-8")
    (kb_root / "kb5.json").write_text('{"inferences":[],"boundary_records":[]}', encoding="utf-8")
    (derived_root / "success_pattern_map.json").write_text('{"角色扮演":["A2-a","A2-b"]}', encoding="utf-8")

    indexes = build_runtime_indexes(str(kb_root))

    assert indexes.category_index.get_cluster_subcategories("A2") == ["A2-a", "A2-b"]
    assert indexes.template_index.find_by_category("A2-a")[0]["template_text"] == "template body"
    assert indexes.success_pattern_index.get_neighbor_subcategories(["角色扮演"]) == ["A2-a", "A2-b"]
