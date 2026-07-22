'use strict';

var BatchApp = {
  taskId: null,
  eventSource: null,
  pollTimer: null,
  themeKey: 'primeiceagi-theme',
  // 实时统计追踪
  stats: {
    startTime: null,
    categoryMap: {},    // { category: { total: N, blocked: N } }
    recentResults: [],  // 最近 20 条结果
    lastCountSnapshot: 0,
    lastSnapshotTime: null,
    throughput: 0       // 条/秒
  }
};

var INTERCEPT_LABEL = {
  'not_blocked': '未拦截',
  'model_refusal': '模型拒答',
  'guardrail_block': '护栏拦截',
  'uncertain': '待定'
};

function formatInterceptType(raw) {
  return INTERCEPT_LABEL[raw] || raw || '-';
}

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

function debounce(fn, delay) {
  var timer = null;
  return function () {
    if (timer) clearTimeout(timer);
    timer = setTimeout(fn, delay);
  };
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
    mode: document.getElementById('batch_mode').value,
    black_dataset_paths: parseLines(document.getElementById('batch_black_dataset_paths').value),
    white_dataset_paths: parseLines(document.getElementById('batch_white_dataset_paths').value),
    guardrail_signatures: collectGuardrailSignatures(),
    exclude_categories: parseCsvList(document.getElementById('batch_exclude_categories').value),
    workers: parseInt(document.getElementById('batch_workers').value, 10) || 1,
    repeat: parseInt(document.getElementById('batch_repeat').value, 10) || 1,
    sleep_seconds: parseFloat(document.getElementById('batch_sleep_seconds').value) || 0,
    retries: parseInt(document.getElementById('batch_retries').value, 10) || 0,
    resume_from_progress: true,
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
  var exportBtn = document.getElementById('batch-btn-export-current');
  if (exportBtn) exportBtn.style.display = BatchApp.taskId ? 'inline-flex' : 'none';
  var resumeBtn = document.getElementById('batch-btn-resume');
  if (resumeBtn && running) resumeBtn.style.display = 'none';
  document.getElementById('batch-progress-card').style.display = 'block';
  if (running) {
    document.getElementById('batch-report-box').style.display = 'none';
  }
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
    review_required_count: summary.review_required_count || 0
  });

  var recentResults = summary.recent_results || [];
  var lastResult = recentResults.length ? recentResults[recentResults.length - 1] : null;
  document.getElementById('batch-last-intercept').textContent = lastResult ? formatInterceptType(lastResult.intercept_type) : '-';
  document.getElementById('batch-last-category').textContent = lastResult ? (lastResult.category_name || lastResult.category || '-') : '-';

  var badges = document.getElementById('batch-report-badges');
  badges.innerHTML = '';
  var counts = summary.intercept_counts || {};
  Object.keys(counts).forEach(function (key) {
    var badge = document.createElement('span');
    badge.className = 'kb-tag';
    badge.textContent = formatInterceptType(key) + ': ' + counts[key];
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
    var reason = item.reason || '-';
    return '<div class="log-line info">'
      + '<span class="log-icon">#</span>'
      + '<span class="log-text">'
      + escapeHtml(item.case_id + ' | ' + category + ' | ' + formatInterceptType(item.intercept_type) + reviewMark + ' | ' + reason)
      + '</span></div>';
  }).join('');
}

function updateReport(report) {
  if (!report) return;
  document.getElementById('batch-report-box').style.display = 'block';
  document.getElementById('batch-report-path').textContent = report.report_file || '';
  updateSummary(report.summary || {});

  // 核心业务指标
  var summary = report.summary || {};
  var interceptRate = summary.guardrail_intercept_rate != null
    ? summary.guardrail_intercept_rate
    : summary.intercept_rate;
  var missRate = summary.guardrail_miss_rate != null
    ? summary.guardrail_miss_rate
    : summary.miss_rate;

  var irEl = document.getElementById('batch-metric-intercept-rate');
  irEl.textContent = interceptRate != null ? (interceptRate * 100).toFixed(1) + '%' : '-';
  irEl.className = 'tile-val' + (interceptRate >= 0.8 ? ' tile-green' : interceptRate >= 0.5 ? ' tile-cyan' : ' tile-red');

  var mrEl = document.getElementById('batch-metric-miss-rate');
  mrEl.textContent = missRate != null ? (missRate * 100).toFixed(1) + '%' : '-';
  mrEl.className = 'tile-val' + (missRate > 0.2 ? ' tile-red' : missRate > 0.1 ? ' tile-orange' : ' tile-green');

  var fpEl = document.getElementById('batch-metric-fp-rate');
  fpEl.textContent = summary.false_positive_rate != null ? (summary.false_positive_rate * 100).toFixed(1) + '%' : '-';
  fpEl.className = 'tile-val' + (summary.false_positive_rate > 0.1 ? ' tile-orange' : ' tile-green');

  var accEl = document.getElementById('batch-metric-accuracy');
  accEl.textContent = summary.accuracy != null ? (summary.accuracy * 100).toFixed(1) + '%' : '-';
  accEl.className = 'tile-val' + (summary.accuracy >= 0.8 ? ' tile-green' : summary.accuracy >= 0.5 ? ' tile-cyan' : ' tile-red');

  // 下载链接
  var download = document.getElementById('batch-download-report');
  var filename = (report.report_file || '').split(/[\\/]/).pop();
  if (BatchApp.taskId && filename) {
    download.href = '/api/batch-eval/' + BatchApp.taskId + '/download/' + encodeURIComponent(filename);
    download.style.display = 'inline-flex';
  }
}

function updateProgressPanel(progress) {
  progress = progress || {};
  var totalCases = progress.total_cases || 0;
  var resultCount = progress.result_count || 0;
  var reviewRequiredCount = progress.review_required_count || 0;
  var percent = totalCases > 0 ? Math.min(100, Math.round((resultCount / totalCases) * 100)) : 0;

  // 进度百分比文本 + 进度条
  var percentText = document.getElementById('batch-progress-percent-text');
  if (percentText) percentText.textContent = percent + '%';
  var progressBarFill = document.getElementById('batch-progressbar-fill');
  if (progressBarFill) progressBarFill.style.width = percent + '%';

  // 已处理
  document.getElementById('batch-processed-count').textContent = resultCount;
  // 元信息
  document.getElementById('batch-progress-meta').textContent = '总样本 ' + totalCases + ' | 已处理 ' + resultCount + ' | 需复核 ' + reviewRequiredCount;

  // 计算吞吐率
  var now = Date.now();
  if (!BatchApp.stats.startTime) BatchApp.stats.startTime = now;
  if (!BatchApp.stats.lastSnapshotTime) {
    BatchApp.stats.lastSnapshotTime = now;
    BatchApp.stats.lastCountSnapshot = resultCount;
  }
  var elapsed = (now - BatchApp.stats.lastSnapshotTime) / 1000;
  if (elapsed >= 3) {
    var delta = resultCount - BatchApp.stats.lastCountSnapshot;
    BatchApp.stats.throughput = delta > 0 ? (delta / elapsed) : BatchApp.stats.throughput;
    BatchApp.stats.lastSnapshotTime = now;
    BatchApp.stats.lastCountSnapshot = resultCount;
  }

  var throughputEl = document.getElementById('batch-throughput');
  if (throughputEl) {
    throughputEl.textContent = BatchApp.stats.throughput > 0 ? BatchApp.stats.throughput.toFixed(2) : '-';
  }

  // 预估剩余时间
  var etaEl = document.getElementById('batch-eta');
  if (etaEl) {
    if (BatchApp.stats.throughput > 0 && totalCases > resultCount) {
      var remaining = totalCases - resultCount;
      var etaSeconds = remaining / BatchApp.stats.throughput;
      etaEl.textContent = formatDuration(etaSeconds);
    } else if (resultCount >= totalCases && totalCases > 0) {
      etaEl.textContent = '已完成';
    } else {
      etaEl.textContent = '-';
    }
  }

  // 更新类别统计表格
  updateCategoryTable();
}

function formatDuration(seconds) {
  if (seconds < 60) return Math.round(seconds) + ' 秒';
  if (seconds < 3600) return Math.round(seconds / 60) + ' 分钟';
  var h = Math.floor(seconds / 3600);
  var m = Math.round((seconds % 3600) / 60);
  return h + ' 小时 ' + m + ' 分钟';
}

function recordResultEvent(data) {
  // 记录到类别统计
  var category = data.category_name || data.category || '未分类';
  if (!BatchApp.stats.categoryMap[category]) {
    BatchApp.stats.categoryMap[category] = { total: 0, blocked: 0 };
  }
  BatchApp.stats.categoryMap[category].total += 1;
  if (data.intercept_type && data.intercept_type !== 'not_blocked') {
    BatchApp.stats.categoryMap[category].blocked += 1;
  }

  // 记录到实时结果流
  BatchApp.stats.recentResults.unshift({
    case_id: data.case_id || '-',
    category: category,
    intercept_type: data.intercept_type || '-',
    reason: data.reason || '',
    time: new Date().toLocaleTimeString('zh-CN', { hour12: false })
  });
  if (BatchApp.stats.recentResults.length > 20) {
    BatchApp.stats.recentResults.length = 20;
  }

  // 更新 UI
  updateRealtimeStream();
  updateCategoryTable();
}

function updateCategoryTable() {
  var box = document.getElementById('batch-category-stats-box');
  var tbody = document.getElementById('batch-category-tbody');
  if (!box || !tbody) return;

  var cats = BatchApp.stats.categoryMap;
  var keys = Object.keys(cats);
  if (!keys.length) {
    box.style.display = 'none';
    return;
  }
  box.style.display = 'block';

  // 按已测数量降序排列
  keys.sort(function (a, b) { return cats[b].total - cats[a].total; });

  var html = '';
  keys.forEach(function (key) {
    var cat = cats[key];
    var rate = cat.total > 0 ? ((cat.blocked / cat.total) * 100).toFixed(1) : '0.0';
    var rateNum = parseFloat(rate);
    var rateClass = rateNum >= 80 ? 'cat-rate-high' : (rateNum >= 50 ? 'cat-rate-mid' : 'cat-rate-low');
    html += '<tr>'
      + '<td>' + escapeHtml(key) + '</td>'
      + '<td>' + cat.total + '</td>'
      + '<td>' + cat.blocked + '</td>'
      + '<td>' + (cat.total - cat.blocked) + '</td>'
      + '<td class="cat-rate ' + rateClass + '">' + rate + '%</td>'
      + '</tr>';
  });
  tbody.innerHTML = html;
}

function updateRealtimeStream() {
  var container = document.getElementById('batch-realtime-stream');
  if (!container) return;

  var results = BatchApp.stats.recentResults;
  var html = '';
  results.forEach(function (item) {
    var resultClass = 'not-blocked';
    if (item.intercept_type !== 'not_blocked') {
      resultClass = 'blocked';
    }
    var resultLabel = formatInterceptType(item.intercept_type);
    html += '<div class="realtime-row">'
      + '<span class="realtime-caseid" title="' + escapeHtml(item.case_id) + '">' + escapeHtml(item.case_id) + '</span>'
      + '<span class="realtime-category">' + escapeHtml(item.category) + '</span>'
      + '<span class="realtime-result ' + resultClass + '">' + escapeHtml(resultLabel) + '</span>'
      + '<span class="realtime-reason" title="' + escapeHtml(item.reason || '') + '">' + escapeHtml(item.reason || '-') + '</span>'
      + '<span class="realtime-time">' + escapeHtml(item.time) + '</span>'
      + '</div>';
  });
  container.innerHTML = html;
}

function resetStats() {
  BatchApp.stats = {
    startTime: null,
    categoryMap: {},
    recentResults: [],
    lastCountSnapshot: 0,
    lastSnapshotTime: null,
    throughput: 0
  };
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
  if (typeof value === 'number') {
    var ts = value < 1e12 ? value * 1000 : value;
    return new Date(ts).toLocaleString('zh-CN', { hour12: false });
  }
  var date = new Date(value);
  if (!isNaN(date.getTime())) {
    return date.toLocaleString('zh-CN', { hour12: false });
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
  if (item.status === 'aborted') {
    actions += ' <button class="btn btn-ghost btn-sm" data-resume-task="' + escapeHtml(taskId) + '">继续执行</button>';
  }

  // 核心指标
  var metricsHtml = '';
  if (summary.accuracy != null) {
    var interceptRate = summary.guardrail_intercept_rate != null ? summary.guardrail_intercept_rate : summary.intercept_rate;
    metricsHtml = '<div class="hint" style="margin-top:4px">'
      + '拦截率 ' + ((interceptRate || 0) * 100).toFixed(1) + '%'
      + ' | 漏报率 ' + ((summary.guardrail_miss_rate || summary.miss_rate || 0) * 100).toFixed(1) + '%'
      + ' | 误报率 ' + ((summary.false_positive_rate || 0) * 100).toFixed(1) + '%'
      + ' | 准确率 ' + ((summary.accuracy || 0) * 100).toFixed(1) + '%'
      + '</div>';
  }

  row.innerHTML = ''
    + '<div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">'
    + '<div><strong>任务 ' + escapeHtml(taskId) + '</strong><div class="hint">状态：' + escapeHtml(status) + ' ｜ 运行时间：' + escapeHtml(runTime) + '</div></div>'
    + '<div class="hint">已处理 ' + escapeHtml(String(processedCases)) + ' / ' + escapeHtml(String(totalCases)) + ' ｜ 需复核 ' + escapeHtml(String(reviewCount)) + '</div>'
    + '</div>'
    + '<div class="hint" style="margin-top:8px">数据集：' + escapeHtml(datasets) + '</div>'
    + metricsHtml
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
      if (!BatchApp.taskId) {
        var running = items.find(function (item) { return item.status === 'running'; });
        if (running) resumeRunningTask(running.task_id);
      }
    })
    .catch(function () {
      container.innerHTML = '<div class="hint">加载历史任务失败</div>';
    });
}

function resumeRunningTask(taskId) {
  BatchApp.taskId = taskId;
  document.getElementById('batch-task-id').textContent = taskId;
  document.getElementById('batch-status-text').textContent = '运行中';
  setRunningState(true);
  connectEventStream(taskId);
  stopPolling();
  BatchApp.pollTimer = setInterval(pollStatus, 3000);
  pollStatus();
  batchLog('页面刷新，已自动恢复任务监听: ' + taskId, 'phase');
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
  // 如果任务未完成（stopped/aborted/异常），显示继续执行按钮
  var resumeBtn = document.getElementById('batch-btn-resume');
  if (resumeBtn) {
    var showResume = BatchApp.taskId && statusText !== '已完成';
    resumeBtn.style.display = showResume ? 'inline-flex' : 'none';
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
        // 如果轮询返回了 last_result，也记录到实时统计（SSE 断开时的后备）
        if (progress.last_result && progress.last_result.case_id) {
          var lr = progress.last_result;
          var lastRecent = BatchApp.stats.recentResults[0];
          if (!lastRecent || lastRecent.case_id !== lr.case_id) {
            recordResultEvent({
              case_id: lr.case_id,
              category: lr.category,
              category_name: lr.category_name,
              intercept_type: lr.intercept_type,
              is_correct: lr.is_correct,
              reason: lr.reason
            });
          }
        }
        if (!data.finished && progress.status) {
          document.getElementById('batch-status-text').textContent = progress.status === 'aborted' ? '已停止' : progress.status;
        }
      }
      if (data.report && data.finished) updateReport(data.report);
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
    case 'progress':
      // SSE 推送的单条结果
      recordResultEvent(event);
      break;
    case 'complete':
      document.getElementById('batch-status-text').textContent = '已完成';
      batchLog('批量评估已完成。', 'success');
      updateReport(event.report || {});
      finalizeBatch('已完成');
      loadBatchHistory();

      // 弹 toast 含关键指标
      var s = (event.report || {}).summary || {};
      var toastMsg = '评估完成: ' + (s.total_cases || 0) + ' 条';
      if (s.accuracy != null) toastMsg += ' | 准确率 ' + (s.accuracy * 100).toFixed(1) + '%';
      batchToast(toastMsg, 'success');

      // 自动滚动到结果区域
      var reportBox = document.getElementById('batch-report-box');
      if (reportBox) reportBox.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
  if (!payload.black_dataset_paths.length) {
    batchToast('请至少填写一个黑样本数据集路径', 'error');
    return;
  }
  var allPaths = payload.black_dataset_paths.concat(payload.white_dataset_paths);
  if (!validateDatasetPaths(allPaths)) {
    return;
  }

  saveFormState();

  BatchApp.taskId = null;
  resetStats();
  document.getElementById('batch-log-stream').innerHTML = '';
  document.getElementById('batch-report-box').style.display = 'none';
  document.getElementById('batch-category-stats-box').style.display = 'none';
  document.getElementById('batch-realtime-stream').innerHTML = '';
  document.getElementById('batch-task-id').textContent = '-';
  document.getElementById('batch-status-text').textContent = '启动中';
  document.getElementById('batch-processed-count').textContent = '0';
  document.getElementById('batch-skipped-count').textContent = '0';
  document.getElementById('batch-throughput').textContent = '-';
  document.getElementById('batch-eta').textContent = '-';
  document.getElementById('batch-progressbar-fill').style.width = '0%';
  document.getElementById('batch-progress-percent-text').textContent = '0%';
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
  var stopBtn = document.getElementById('batch-btn-stop');
  stopBtn.disabled = true;
  stopBtn.textContent = '正在停止...';
  fetch('/api/batch-eval/' + BatchApp.taskId + '/stop', { method: 'POST' })
    .then(function () {
      batchLog('已发送停止请求。', 'warn');
      document.getElementById('batch-status-text').textContent = '停止中';
    })
    .catch(function () {
      batchToast('停止请求发送失败', 'error');
      stopBtn.disabled = false;
      stopBtn.textContent = '终止任务';
    });
}

function exportCurrentReport() {
  if (!BatchApp.taskId) {
    batchToast('当前无运行中的任务', 'error');
    return;
  }
  batchLog('正在导出当前已完成结果的报告...', 'info');
  fetch('/api/batch-eval/' + BatchApp.taskId + '/export-current', { method: 'POST' })
    .then(function (r) { return r.json(); })
    .then(function (response) {
      if (!response.ok) throw new Error(response.error || '导出失败');
      var data = response.data || {};
      batchToast('报告已生成，共 ' + (data.summary && data.summary.processed_cases || '?') + ' 条结果', 'success');
      batchLog('当前报告导出成功。', 'success');
      if (data.download_url) {
        window.open(data.download_url, '_blank');
      }
    })
    .catch(function (error) {
      batchToast(error.message || '导出失败', 'error');
      batchLog('导出失败: ' + (error.message || '未知错误'), 'error');
    });
}

function resumeBatchEval(taskId) {
  // 从 localStorage 表单状态中提取 API key（磁盘上没有）
  var formState = safeJsonParse(localStorage.getItem(FORM_STORAGE_KEY), {});
  var credentials = {
    target_api_key: formState.target_api_key || document.getElementById('target_api_key').value.trim(),
    agent_api_key: formState.agent_api_key || document.getElementById('agent_api_key').value.trim(),
    target_api_url: formState.target_api_url || document.getElementById('target_api_url').value.trim(),
    agent_api_url: formState.agent_api_url || document.getElementById('agent_api_url').value.trim()
  };

  if (!credentials.target_api_key) {
    batchToast('请先填写目标模型 API Key 后再续跑', 'error');
    return;
  }

  if (!confirm('确认续跑任务 ' + taskId + '？\n将从上次中断处继续，需要有效的 API Key。')) {
    return;
  }

  resetStats();
  document.getElementById('batch-log-stream').innerHTML = '';
  document.getElementById('batch-status-text').textContent = '续跑中';
  document.getElementById('batch-report-box').style.display = 'none';
  setRunningState(true);
  batchLog('正在续跑任务: ' + taskId, 'phase');

  fetch('/api/batch-eval/' + encodeURIComponent(taskId) + '/resume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(credentials)
  })
    .then(function (r) { return r.json(); })
    .then(function (response) {
      if (!response.ok) throw new Error(response.error || '续跑失败');
      BatchApp.taskId = taskId;
      document.getElementById('batch-task-id').textContent = taskId;
      document.getElementById('batch-status-text').textContent = '运行中';
      connectEventStream(taskId);
      stopPolling();
      BatchApp.pollTimer = setInterval(pollStatus, 3000);
      pollStatus();
      batchLog('续跑中 — 加载已有进度，跳过已完成的用例...', 'info');
    })
    .catch(function (error) {
      batchToast(error.message || '续跑失败', 'error');
      batchLog('续跑失败: ' + (error.message || '未知错误'), 'error');
      finalizeBatch('续跑失败');
    });
}

function toggleCustomTemplateFields() {
  var templateName = document.getElementById('template_name').value;
  var container = document.getElementById('custom-template-fields');
  if (container) {
    container.style.display = templateName === 'custom' ? 'contents' : 'none';
  }
}

function toggleCardCollapse(cardEl) {
  var body = cardEl.querySelector('.card-body');
  if (!body) return;
  var isCollapsed = body.style.display === 'none';
  body.style.display = isCollapsed ? '' : 'none';
  var icon = cardEl.querySelector('.collapse-icon');
  if (icon) icon.textContent = isCollapsed ? '▼' : '▶';
}

document.addEventListener('click', function (event) {
  // 折叠卡片点击
  var collapseTitle = event.target.closest('[data-collapsible]');
  if (collapseTitle) {
    if (collapseTitle.classList.contains('card-subsection-title')) {
      var subsectionBody = collapseTitle.nextElementSibling;
      if (subsectionBody && subsectionBody.classList.contains('card-subsection-body')) {
        var isCollapsed = subsectionBody.style.display === 'none';
        subsectionBody.style.display = isCollapsed ? '' : 'none';
        var icon = collapseTitle.querySelector('.collapse-icon');
        if (icon) icon.textContent = isCollapsed ? '▼' : '▶';
      }
    } else {
      var card = collapseTitle.closest('.card');
      if (card) toggleCardCollapse(card);
    }
    return;
  }

  var historyButton = event.target.closest('[data-history-report]');
  if (historyButton) {
    loadHistoryReport(historyButton.getAttribute('data-history-report'));
    return;
  }

  var resumeButton = event.target.closest('[data-resume-task]');
  if (resumeButton) {
    resumeBatchEval(resumeButton.getAttribute('data-resume-task'));
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
  var themeBtn = document.querySelector('.theme-toggle');
  if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
  document.getElementById('batch-btn-start').addEventListener('click', startBatchEval);
  document.getElementById('batch-btn-stop').addEventListener('click', stopBatchEval);
  document.getElementById('batch-btn-resume').addEventListener('click', function() {
    if (BatchApp.taskId) resumeBatchEval(BatchApp.taskId);
  });
  var exportCurrentBtn = document.getElementById('batch-btn-export-current');
  if (exportCurrentBtn) exportCurrentBtn.addEventListener('click', exportCurrentReport);
  document.getElementById('btn-add-signature').addEventListener('click', addSignatureRow);
  document.getElementById('batch_mode').addEventListener('change', function () {
    toggleGuardrailCard();
    saveFormState();
  });

  // 先恢复表单状态
  restoreFormState();
  // 恢复后再根据模式显示/隐藏护栏卡片
  toggleGuardrailCard();
  // 自定义模板字段显隐
  toggleCustomTemplateFields();

  // template_name 变更时切换自定义字段显隐
  document.getElementById('template_name').addEventListener('change', function () {
    toggleCustomTemplateFields();
    saveFormState();
  });

  // 自动保存：表单字段变化时自动保存状态
  FORM_FIELDS.forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', saveFormState);
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.addEventListener('input', debounce(saveFormState, 1000));
    }
  });

  loadBatchHistory();
});

function toggleGuardrailCard() {
  var mode = document.getElementById('batch_mode').value;
  var card = document.getElementById('guardrail-signature-card');
  card.style.display = mode === 'guardrail' ? 'block' : 'none';
}

function addSignatureRow() {
  var container = document.getElementById('guardrail-signatures-list');
  var row = document.createElement('div');
  row.className = 'signature-row form-grid';
  row.style.marginBottom = '8px';
  row.innerHTML = ''
    + '<div class="form-group"><select class="sig-type">'
    + '<option value="json_field">JSON字段包含</option>'
    + '<option value="text_contains">文本包含</option>'
    + '<option value="regex">正则匹配</option>'
    + '</select></div>'
    + '<div class="form-group" style="flex:2"><input class="sig-pattern" placeholder="例: &quot;code&quot;:200 或 内容违规 或 block(ed)?" /></div>'
    + '<div class="form-group" style="flex:0"><button class="btn btn-ghost btn-sm btn-remove-sig" title="删除">&times;</button></div>';
  container.appendChild(row);
  row.querySelector('.btn-remove-sig').addEventListener('click', function () {
    row.remove();
  });
}

function collectGuardrailSignatures() {
  var rows = document.querySelectorAll('#guardrail-signatures-list .signature-row');
  var signatures = [];
  rows.forEach(function (row) {
    var type = row.querySelector('.sig-type').value;
    var pattern = row.querySelector('.sig-pattern').value.trim();
    if (pattern) {
      signatures.push({ type: type, pattern: pattern });
    }
  });
  return signatures;
}

var FORM_STORAGE_KEY = 'batcheval-form-state';

var FORM_FIELDS = [
  'batch_mode', 'batch_black_dataset_paths', 'batch_white_dataset_paths',
  'batch_exclude_categories', 'batch_workers', 'batch_repeat',
  'batch_sleep_seconds', 'batch_retries', 'batch_enable_llm_judge',
  'batch_output_file', 'template_name', 'target_api_url', 'target_api_key',
  'target_model', 'target_temperature', 'target_top_p',
  'agent_api_url', 'agent_api_key', 'agent_model',
  'custom_headers', 'custom_body', 'custom_method', 'custom_timeout',
  'custom_content_path', 'custom_reasoning_path'
];

function saveFormState() {
  var state = {};
  FORM_FIELDS.forEach(function (id) {
    var el = document.getElementById(id);
    if (el) state[id] = el.value;
  });
  state._signatures = collectGuardrailSignatures();
  localStorage.setItem(FORM_STORAGE_KEY, JSON.stringify(state));
}

function restoreFormState() {
  var raw = localStorage.getItem(FORM_STORAGE_KEY);
  if (!raw) return;
  var state = safeJsonParse(raw, null);
  if (!state) return;

  // 先恢复所有普通字段
  FORM_FIELDS.forEach(function (id) {
    if (state[id] == null) return;
    var el = document.getElementById(id);
    if (!el) return;
    el.value = state[id];
  });

  // 清除已有的签名行再恢复
  var sigContainer = document.getElementById('guardrail-signatures-list');
  if (sigContainer) sigContainer.innerHTML = '';

  // 恢复护栏签名
  if (state._signatures && state._signatures.length) {
    state._signatures.forEach(function (sig) {
      addSignatureRow();
      var rows = document.querySelectorAll('#guardrail-signatures-list .signature-row');
      var lastRow = rows[rows.length - 1];
      if (lastRow) {
        lastRow.querySelector('.sig-type').value = sig.type;
        lastRow.querySelector('.sig-pattern').value = sig.pattern;
      }
    });
  }
}
