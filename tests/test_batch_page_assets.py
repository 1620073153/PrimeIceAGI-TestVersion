from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_batch_js_contains_dataset_extension_validation_and_history_loading():
    script = (PROJECT_ROOT / "static" / "js" / "batch.js").read_text(encoding="utf-8")

    assert "仅支持 .csv 或 .xlsx 数据集文件" in script
    assert "/api/batch-eval/history" in script
    assert "batch-history-list" in script
    assert "processed_cases" in script
    assert "loadBatchHistory" in script
    assert "case 'aborted':" in script
    assert "data.progress" in script
    assert "formatHistoryStatus" in script
    assert "查看摘要" in script
    assert "dataset_paths" in script
    assert "/report" in script
    assert "batch-progress-percent" in script
    assert "batch-current-case" in script
    assert "batch-last-reason" in script
    assert "Math.min(100" in script
    assert "limit=20" in script


def test_app_js_surfaces_project_local_claude_status():
    script = (PROJECT_ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert "var status = data.status || {};" in script
    assert "st.textContent = status.message || '';" in script
    assert "st.style.color = status.ready ? 'var(--success)' : 'var(--warning)';" in script
    assert "setTimeout(function () { loadClaudeCfg(); }, 100);" in script
