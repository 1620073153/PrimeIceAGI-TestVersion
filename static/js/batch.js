'use strict';

var BatchApp = {
  taskId: null,
  eventSource: null,
  pollTimer: null,
  themeKey: 'primeiceagi-theme'
};

function batchToast(message, type) {
  var el = document.createElement('div');
  el.className = 'toast ' + (type || 'info');
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(function () { el.style.opacity = '0'; el.style.transition = 'opacity .4s'; }, 3200);
  setTimeout(function () { el.remove(); }, 3800);
}

function batchLog(message, type) {
  var stream = document.getElementById('batch-log-stream');
  if (!stream) return;
  var line = document.createElement('div');
  line.className = 'log-line ' + (type || 'info');
  line.innerHTML = '<span class="log-icon">&#183;</span><span class="log-text">' + escapeHtml(message) + '</span>';
  stream.appendChild(line);
  stream.scrollTop = stream.scrollHeight;
}

function escapeHtml(text) {
  var div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function getTheme() {
  return localStorage.getItem(BatchApp.themeKey) || 'dark';
}

function applyTheme(theme) {
  document.body.classList.toggle('theme-light', theme === 'light');
  var button = document.querySelector('.theme-toggle');
  if (button) button.innerHTML = theme === 'light' ? '&#9788;' : '&#9790;';
  localStorage.setItem(BatchApp.themeKey, theme);
}

function toggleTheme() {
  applyTheme(getTheme() === 'dark' ? 'light' : 'dark');
}

function parseLines(value) {
  return (value || '')
    .split(/\r?\n/)
    .map(function (item) { return item.trim(); })
    .filter(Boolean);
}

function parseCsvList(value) {
  return (value || '')
    .split(',')
    .map(function (item) { return item.trim(); })
    .filter(Boolean);
}

function isAllowedDatasetPath(path) {
  return /\.(csv|xlsx)$/i.test(path || '');
}

function validateDatasetPaths(paths) {
  var invalid = paths.filter(function (path) {
    return !isAllowedDatasetPath(path);
  });
  if (invalid.length) {
    batchToast('仅支持 .csv 或 .xlsx 数据集文件', 'error');
    return false;
  }
  return true;
}

function safeJsonParse(text, fallback) {
  try {
    return text ? JSON.parse(text) : fallback;
  } catch (error) {
    return fallback;
  }
}

function buildBatchPayload() {
  var payload = {
    dataset_paths: parseLines(document.getElementById('batch_dataset_paths').value),
    exclude_categories: parseCsvList(document.getElementById('batch_exclude_categories').value),
    workers: parseInt(document.getElementById('batch_workers').value, 10) || 1,
    repeat: parseInt(document.getElementById('batch_repeat').value, 10) || 1,
    sleep_seconds: parseFloat(document.getElementById('batch_sleep_seconds').value) || 0,
    retries: parseInt(document.getElementById('batch_retries').value, 10) || 0,
    resume_from_progress: document.getElementById('batch_resume').value === 'true',
    enable_llm_judge: document.getElementById('batch_enable_llm_judge').value === 'true',
    output_file: (document.getElementById('batch_output_file').value || 'batch-report.xlsx').trim(),
    template_name: document.getElementById('template_name').value,
    target_api_url: document.getElementById('target_api_url').value.trim(),
    target_api_key: document.getElementById('target_api_key').value.trim(),
    target_model: document.getElementById('target_model').value.trim(),
    agent_api_url: document.getElementById('agent_api_url').value.trim(),
    agent_api_key: document.getElementById('agent_api_key').value.trim(),
    agent_model: document.getElementById('agent_model').value.trim()
  };

  var temperature = parseFloat(document.getElementById('target_temperature').value);
  if (!isNaN(temperature)) payload.temperature = temperature;
  var topP = parseFloat(document.getElementById('target_top_p').value);
  if (!isNaN(topP)) payload.top_p = topP;

  if (payload.template_name === 'custom') {
    payload.method = document.getElementById('custom_method').value;
    payload.timeout = parseInt(document.getElementById('custom_timeout').value, 10) || 120;
    payload.headers = safeJsonParse(document.getElementById('custom_headers').value, {});
    payload.body = safeJsonParse(document.getElementById('custom_body').value, {});
    payload.response_path = {
      content: document.getElementById('custom_content_path').value.trim(),
      reasoning: document.getElementById('custom_reasoning_path').value.trim()
    };
  }

  return payload;
}

function setRunningState(running) {
  document.getElementById('batch-btn-start').disabled = running;
  document.getElementById('batch-btn-stop').style.display = running ? 'inline-flex' : 'none';
  document.getElementById('batch-progress-card').style.display = 'block';
}

function updateSummary(summary) {
  summary = summary || {};
  document.getElementById('batch-processed-count').textContent = summary.processed_cases || 0;
  document.getElementById('batch-skipped-count').textContent = summary.skipped_cases || 0;
  document.getElementById('batch-total-count').textContent = summary.total_cases || 0;
  document.getElementById('batch-review-count').textContent = summary.review_required_count || 0;
  updateProgressPanel({
    total_cases: summary.total_cases || 0,
    result_count: summary.processed_cases || 0,
    review_required_count: summary.review_required_count || 0,
    current_case_id: null,
    last_result: (summary.recent_results || []).length ? summary.recent_results[summary.recent_results.length - 1] : null
  });

  var recentResults = summary.recent_results || [];
  var lastResult = recentResults.length ? recentResults[recentResults.length - 1] : null;
  document.getElementById('batch-last-intercept').textContent = lastResult ? lastResult.intercept_type : '-';
  document.getElementById('batch-last-category').textContent = lastResult && lastResult.category ? lastResult.category : '-';

  var badges = document.getElementById('batch-report-badges');
  badges.innerHTML = '';
  var counts = summary.intercept_counts || {};
  Object.keys(counts).forEach(function (key) {
    var badge = document.createElement('span');
    badge.className = 'kb-tag';
    badge.textContent = key + ': ' + counts[key];
    badges.appendChild(badge);
  });

  var recentList = document.getElementById('batch-recent-results');
  if (!recentResults.length) {
    recentList.className = 'hint';
    recentList.innerHTML = '任务完成后显示最近 10 条样本结论。';
    return;
  }

  recentList.className = '';
  recentList.innerHTML = recentResults.map(function (item) {
    var reviewMark = item.review_required ? ' [需复核]' : '';
    var category = item.category || '-';
    var reason = item.judge_reason || '-';
    return '<div class="log-line info">'
      + '<span class="log-icon">#</span>'
      + '<span class="log-text">'
      + escapeHtml(item.case_id + ' | ' + category + ' | ' + item.intercept_type + reviewMark + ' | ' + reason)
      + '</span></div>';
  }).join('');
}

function updateReport(report) {
  if (!report) return;
  document.getElementById('batch-report-box').style.display = 'block';
  document.getElementById('batch-report-path').textContent = report.report_file || '';
  updateSummary(report.summary || {});

  var download = document.getElementById('batch-download-report');
  var filename = (report.report_file || '').split(/[\\/]/).pop();
  if (BatchApp.taskId && filename) {
    download.href = '/api/batch-eval/' + BatchApp.taskId + '/download/' + encodeURIComponent(filename);
  }
}

function updateProgressPanel(progress) {
  progress = progress || {};
  var totalCases = progress.total_cases || 0;
  var resultCount = progress.result_count || 0;
  var reviewRequiredCount = progress.review_required_count || 0;
  var percent = totalCases > 0 ? Math.min(100, Math.round((resultCount / totalCases) * 100)) : 0;
  var lastResult = progress.last_result || null;

  document.getElementById('batch-progress-percent').textContent = percent + '%';
  document.getElementById('batch-current-case').textContent = progress.current_case_id || '-';
  document.getElementById('batch-last-result').textContent = lastResult ? (lastResult.intercept_type || '-') : '-';
  document.getElementById('batch-last-reason').textContent = lastResult ? (lastResult.judge_reason || '-') : '-';
  document.getElementById('batch-progress-meta').textContent = '总样本 ' + totalCases + ' ｜ 已处理 ' + resultCount + ' ｜ 需复核 ' + reviewRequiredCount;
}

function formatHistoryStatus(status) {
  switch (status) {
    case 'completed': return '已完成';
    case 'running': return '运行中';
    case 'aborted': return '已停止';
    case 'error': return '异常';
    default: return status || '-';
  }
}

function formatHistoryTime(value) {
  if (!value) return '-';
  var date = new Date(value);
  if (!isNaN(date.getTime())) {
    return date.toLocaleString('zh-CN', { hour12: false });
  }
  if (typeof value === 'number') {
    return new Date(value * 1000).toLocaleString('zh-CN', { hour12: false });
  }
  return String(value);
}

function loadHistoryReport(taskId) {
  fetch('/api/batch-eval/' + encodeURIComponent(taskId) + '/report')
    .then(function (r) { return r.json(); })
    .then(function (response) {
      if (!response.ok) throw new Error(response.error || '读取摘要失败');
      BatchApp.taskId = taskId;
      document.getElementById('batch-task-id').textContent = taskId;
      document.getElementById('batch-progress-card').style.display = 'block';
      updateReport(response.data || {});
      batchToast('已加载历史任务摘要', 'info');
    })
    .catch(function (error) {
      batchToast(error.message || '读取摘要失败', 'error');
    });
}

function renderBatchHistoryItem(item) {
  var row = document.createElement('div');
  row.className = 'chart-box';
  var taskId = item.task_id || '-';
  var status = formatHistoryStatus(item.status);
  var summary = item.summary || {};
  var progress = item.progress || {};
  var processedCases = summary.processed_cases != null ? summary.processed_cases : (progress.result_count || 0);
  var totalCases = summary.total_cases != null ? summary.total_cases : (progress.total_cases || 0);
  var reviewCount = summary.review_required_count != null ? summary.review_required_count : (progress.review_required_count || 0);
  var runTime = formatHistoryTime(item.last_updated_at || item.created_at);
  var datasets = (item.dataset_paths || []).join('；') || '-';
  var reportFile = item.report_file || '';
  var actions = '';
  if (reportFile) {
    var filename = reportFile.split(/[\\/]/).pop();
    var link = '/api/batch-eval/' + encodeURIComponent(taskId) + '/download/' + encodeURIComponent(filename);
    actions += '<a class="btn btn-primary btn-sm" href="' + link + '" target="_blank" rel="noopener">下载</a>';
    actions += ' <button class="btn btn-ghost btn-sm" data-history-report="' + escapeHtml(taskId) + '">查看摘要</button>';
  }
  row.innerHTML = ''
    + '<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">'
    + '<div><strong>任务 ' + escapeHtml(taskId) + '</strong><div class="hint">状态：' + escapeHtml(status) + ' ｜ 运行时间：' + escapeHtml(runTime) + '</div></div>'
    + '<div class="hint">已处理 ' + escapeHtml(String(processedCases)) + ' / ' + escapeHtml(String(totalCases)) + ' ｜ 需复核 ' + escapeHtml(String(reviewCount)) + '</div>'
    + '</div>'
    + '<div class="hint" style="margin-top:8px">数据集：' + escapeHtml(datasets) + '</div>'
    + (actions ? '<div class="actions" style="margin-top:10px;padding-top:10px">' + actions + '</div>' : '');
  return row;
}

function loadBatchHistory() {
  var container = document.getElementById('batch-history-list');
  if (!container) return;
  fetch('/api/batch-eval/history?limit=20')
    .then(function (r) { return r.json(); })
    .then(function (response) {
      var items = response.data || [];
      container.innerHTML = '';
      if (!items.length) {
        container.innerHTML = '<div class="hint">暂无历史任务</div>';
        return;
      }
      items.forEach(function (item) {
        container.appendChild(renderBatchHistoryItem(item));
      });
    })
    .catch(function () {
      container.innerHTML = '<div class="hint">加载历史任务失败</div>';
    });
}

function stopPolling() {
  if (BatchApp.pollTimer) {
    clearInterval(BatchApp.pollTimer);
    BatchApp.pollTimer = null;
  }
}

function finalizeBatch(statusText) {
  if (statusText) document.getElementById('batch-status-text').textContent = statusText;
  setRunningState(false);
  stopPolling();
  if (BatchApp.eventSource) {
    BatchApp.eventSource.close();
    BatchApp.eventSource = null;
  }
}

function pollStatus() {
  if (!BatchApp.taskId) return;
  fetch('/api/batch-eval/' + BatchApp.taskId + '/status')
    .then(function (r) { return r.json(); })
    .then(function (payload) {
      var data = payload.data || payload;
      if (data.progress) {
        var progress = data.progress;
        document.getElementById('batch-processed-count').textContent = progress.result_count || 0;
        document.getElementById('batch-skipped-count').textContent = Math.max((progress.total_cases || 0) - (progress.result_count || 0), 0);
        updateProgressPanel(progress);
        if (!data.finished && progress.status) {
          document.getElementById('batch-status-text').textContent = progress.status === 'aborted' ? '已停止' : progress.status;
        }
      }
      if (data.report) updateReport(data.report);
      if (data.finished) {
        document.getElementById('batch-status-text').textContent = data.stopped ? '已停止' : '已完成';
        finalizeBatch(data.stopped ? '已停止' : '已完成');
      }
    })
    .catch(function () { /* 静默轮询失败 */ });
}

function connectEventStream(taskId) {
  if (BatchApp.eventSource) BatchApp.eventSource.close();
  BatchApp.eventSource = new EventSource('/api/batch-eval/' + taskId + '/stream');
  BatchApp.eventSource.onmessage = function (event) {
    var data = JSON.parse(event.data);
    handleBatchEvent(data);
  };
  BatchApp.eventSource.onerror = function () {
    batchLog('事件流连接中断，继续通过状态轮询获取结果。', 'warn');
    if (BatchApp.eventSource) {
      BatchApp.eventSource.close();
      BatchApp.eventSource = null;
    }
  };
}

function handleBatchEvent(event) {
  if (!event || !event.event) return;
  if (event.event === 'heartbeat') return;

  switch (event.event) {
    case 'started':
      document.getElementById('batch-status-text').textContent = '运行中';
      batchLog('任务已启动：' + (event.task_id || BatchApp.taskId), 'phase');
      break;
    case 'complete':
      document.getElementById('batch-status-text').textContent = '已完成';
      batchLog('批量评估已完成。', 'success');
      updateReport(event.report || {});
      finalizeBatch('已完成');
      loadBatchHistory();
      break;
    case 'aborted':
      document.getElementById('batch-status-text').textContent = '已停止';
      batchLog(event.reason || '批量评估已停止。', 'warn');
      updateReport(event.report || {});
      finalizeBatch('已停止');
      loadBatchHistory();
      break;
    case 'error':
      document.getElementById('batch-status-text').textContent = '异常';
      batchLog(event.message || '批量评估异常', 'error');
      batchToast(event.message || '批量评估异常', 'error');
      finalizeBatch('异常');
      break;
    default:
      batchLog(event.message || ('收到事件: ' + event.event), 'info');
      break;
  }
}

function startBatchEval() {
  var payload = buildBatchPayload();
  if (!payload.dataset_paths.length) {
    batchToast('请至少填写一个数据集路径', 'error');
    return;
  }
  if (!validateDatasetPaths(payload.dataset_paths)) {
    return;
  }

  BatchApp.taskId = null;
  document.getElementById('batch-log-stream').innerHTML = '';
  document.getElementById('batch-report-box').style.display = 'none';
  document.getElementById('batch-task-id').textContent = '-';
  document.getElementById('batch-status-text').textContent = '启动中';
  document.getElementById('batch-processed-count').textContent = '0';
  document.getElementById('batch-skipped-count').textContent = '0';
  setRunningState(true);
  batchLog('正在提交批量评估任务...', 'phase');

  fetch('/api/batch-eval/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
    .then(function (r) { return r.json(); })
    .then(function (response) {
      if (!response.ok) throw new Error(response.error || '启动失败');
      var data = response.data || {};
      BatchApp.taskId = data.task_id;
      document.getElementById('batch-task-id').textContent = BatchApp.taskId || '-';
      document.getElementById('batch-status-text').textContent = '运行中';
      connectEventStream(BatchApp.taskId);
      stopPolling();
      BatchApp.pollTimer = setInterval(pollStatus, 3000);
    })
    .catch(function (error) {
      batchToast(error.message || '启动失败', 'error');
      batchLog('启动失败: ' + (error.message || '未知错误'), 'error');
      finalizeBatch('启动失败');
    });
}

function stopBatchEval() {
  if (!BatchApp.taskId) return;
  fetch('/api/batch-eval/' + BatchApp.taskId + '/stop', { method: 'POST' })
    .then(function () {
      batchLog('已发送停止请求。', 'warn');
      document.getElementById('batch-status-text').textContent = '停止中';
    })
    .catch(function () {
      batchToast('停止请求发送失败', 'error');
    });
}

document.addEventListener('click', function (event) {
  var historyButton = event.target.closest('[data-history-report]');
  if (historyButton) {
    loadHistoryReport(historyButton.getAttribute('data-history-report'));
    return;
  }

  var button = event.target.closest('[data-toggle-pw]');
  if (!button) return;
  var input = document.getElementById(button.getAttribute('data-toggle-pw'));
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    button.classList.add('active');
  } else {
    input.type = 'password';
    button.classList.remove('active');
  }
});

document.addEventListener('DOMContentLoaded', function () {
  applyTheme(getTheme());
  document.querySelector('.theme-toggle').addEventListener('click', toggleTheme);
  document.getElementById('batch-btn-start').addEventListener('click', startBatchEval);
  document.getElementById('batch-btn-stop').addEventListener('click', stopBatchEval);
  loadBatchHistory();
});
