from engine.knowledge.kb_index import build_runtime_indexes


def test_build_runtime_indexes_exposes_category_cluster_template_and_success_maps(tmp_path):
    kb_root = tmp_path / "kb_data"
    derived_root = kb_root / "derived"
    derived_root.mkdir(parents=True)

    (kb_root / "kb1.json").write_text('{"categories":{"B":{"subcategories":{"B-1":{},"B-2":{}}},"C":{"subcategories":{"C-1":{}}}},"clusters":{"B":{"cross_cluster":["C"]}}}', encoding="utf-8")
    (kb_root / "kb2.json").write_text('{"concepts":{"role_play":{}}}', encoding="utf-8")
    (kb_root / "kb3.json").write_text('{"methods":{"authority_framing":{}},"signal_strategy_map":{},"concept_method_map":{"role_play":["authority_framing"]}}', encoding="utf-8")
    (kb_root / "kb4.json").write_text('{"templates":{"t1":{"category":"B-1","tags":["role_play"],"template_text":"template body"}}}', encoding="utf-8")
    (kb_root / "kb5.json").write_text('{"inferences":[],"boundary_records":[]}', encoding="utf-8")
    (derived_root / "success_pattern_map.json").write_text('{"role_play":["B-1","B-2"]}', encoding="utf-8")

    indexes = build_runtime_indexes(str(kb_root))

    assert indexes.category_index.get_cluster_subcategories("B") == ["B-1", "B-2"]
    assert indexes.cluster_index.get_cross_cluster_subcategories("B") == ["C-1"]
    assert indexes.template_index.find_by_category("B-1")[0]["template_text"] == "template body"
    assert indexes.success_pattern_index.get_neighbor_subcategories(["role_play"]) == ["B-1", "B-2"]
