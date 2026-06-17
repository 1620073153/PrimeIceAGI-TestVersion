'use strict';

var App = {
  taskId: null,
  eventSource: null,
  allRounds: [],
  currentRound: 0,
  pollTimer: null,
  elapsedTimer: null,
  elapsedStart: 0,
  trackCount: 0,
  THEME_KEY: 'primeiceagi-theme',
  maxRounds: function () { return parseInt(document.getElementById('max_rounds').value) || 5; }
};

/* ── Logging ── */
var Log = {
  add: function (text, cls) {
    var el = document.getElementById('log-stream');
    var icons = { success: '&#10004;', error: '&#10008;', warn: '&#9888;', info: '&#9679;', phase: '&#9654;' };
    var line = document.createElement('div');
    line.className = 'log-line ' + (cls || '');
    line.innerHTML = '<span class="log-icon">' + (icons[cls] || '&#183;') + '</span><span class="log-text">' + text + '</span>';
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
  },
  clear: function () { document.getElementById('log-stream').innerHTML = ''; }
};

/* ── Track Lanes ── */
var Tracks = {
  init: function (count) {
    App.trackCount = count;
    var el = document.getElementById('track-lanes');
    el.innerHTML = '';
    for (var i = 0; i < count; i++) {
      el.innerHTML += '<div class="track-lane" id="track-' + i + '">' +
        '<span class="track-label">#' + (i + 1).toString().padStart(2, '0') + '</span>' +
        '<div class="track-bar"><div class="track-bar-fill pending" id="track-bar-' + i + '" style="width:50%"></div></div>' +
        '<span class="track-time" id="track-time-' + i + '">...</span>' +
        '<span class="track-status waiting" id="track-status-' + i + '">等待</span></div>';
    }
  },
  updateLabel: function (idx, label) {
    var el = document.querySelector('#track-' + idx + ' .track-label');
    if (el) el.textContent = label;
  },
  done: function (idx, status, latency) {
    var bar = document.getElementById('track-bar-' + idx);
    var time = document.getElementById('track-time-' + idx);
    var stat = document.getElementById('track-status-' + idx);
    if (!bar) return;
    bar.style.width = '100%';
    bar.className = 'track-bar-fill ' + status;
    time.textContent = (latency / 1000).toFixed(1) + 's';
    var labels = { bypassed: '绕过', blocked: '拒绝', guardrail: '护栏', false_positive: '假阳性' };
    stat.textContent = labels[status] || status;
    stat.className = 'track-status ' + status;
  },
  setJudging: function (idx) {
    var stat = document.getElementById('track-status-' + idx);
    if (stat) { stat.textContent = '裁判中'; stat.className = 'track-status judging'; }
  }
};

/* ── Session Pool ── */
var Sessions = {
  update: function (sessions, killed) {
    var pool = document.getElementById('session-pool');
    if (!sessions || sessions.length === 0) { pool.style.display = 'none'; return; }
    pool.style.display = 'flex';
    var html = '<span class="session-pool-label">存活会话 [' + sessions.length + '/5]:</span>';
    sessions.forEach(function (s) {
      html += '<span class="session-chip">' + s.id + ' (' + s.turn_num + '轮)</span>';
    });
    if (killed && killed.length) {
      killed.forEach(function (k) {
        html += '<span class="session-chip dead">' + k + '</span>';
      });
    }
    pool.innerHTML = html;
  }
};

/* ── EventBus ── */
var EventBus = {
  _retryCount: 0,
  _maxRetries: 5,
  connect: function (taskId) {
    if (App.eventSource) App.eventSource.close();
    EventBus._retryCount = 0;
    EventBus._openSSE(taskId);
  },
  _openSSE: function (taskId) {
    App.eventSource = new EventSource('/api/test/' + taskId + '/stream');
    App.eventSource.onmessage = function (e) { EventBus.handleEvent(JSON.parse(e.data)); };
    App.eventSource.onerror = function () {
      if (!App.taskId) { App.eventSource.close(); return; }
      App.eventSource.close();
      if (EventBus._retryCount < EventBus._maxRetries) {
        EventBus._retryCount++;
        Log.add('SSE 断开，3秒后重连 (' + EventBus._retryCount + '/' + EventBus._maxRetries + ')', 'warn');
        setTimeout(function () { EventBus._openSSE(taskId); }, 3000);
      } else {
        Log.add('SSE 重连失败，切换到轮询模式', 'warn');
        EventBus.startPolling(taskId);
      }
    };
  },
  startPolling: function (tid) {
    EventBus.stopPolling();
    App.pollTimer = setInterval(function () {
      fetch('/api/test/' + tid + '/status').then(function (r) { return r.json(); }).then(function (d) {
        if (d.finished && d.report) {
          EventBus.stopPolling();
          App.allRounds = d.report.rounds || [];
          document.getElementById('rounds-container').innerHTML = '';
          App.allRounds.forEach(renderRoundCard);
          updateFinalSummary();
          finalize();
        }
      }).catch(function () { /* 轮询静默失败，避免打扰用户 */ });
    }, 3000);
  },
  stopPolling: function () { if (App.pollTimer) { clearInterval(App.pollTimer); App.pollTimer = null; } },

  handleEvent: function (evt) {
    switch (evt.event) {
      case 'round_start':
        App.currentRound = evt.round;
        document.getElementById('live-round').textContent = 'R' + evt.round;
        document.getElementById('live-phase').textContent = '提示词生成中...';
        Log.add('第 ' + evt.round + '/' + evt.total_rounds + ' 轮开始', 'phase');
        if (evt.active_sessions && evt.active_sessions.length) {
          Log.add('存活会话: ' + evt.active_sessions.join(', '), 'info');
        }
        break;
<!-- SPLIT_JS_1 -->
      case 'generating':
        document.getElementById('live-phase').textContent = '智能体生成中...';
        Log.add('Agent1 生成提示词...', 'info');
        break;
      case 'prompts_ready':
        document.getElementById('live-phase').textContent = '并发调用 (' + evt.total + '路)';
        Log.add('生成完成: ' + evt.new_count + '条新攻' + (evt.cont_count > 0 ? ' + ' + evt.cont_count + '条续攻' : ''), 'success');
        Tracks.init(evt.total);
        break;
      case 'testing':
        document.getElementById('live-phase').textContent = '调用待测模型 (' + evt.count + '路)...';
        break;
      case 'single_done':
        var label = '#' + (evt.index + 1).toString().padStart(2, '0');
        if (evt.type === 'continue') label += ' [续·' + evt.session_id + ']';
        else label += ' [新攻]';
        Tracks.updateLabel(evt.index, label);
        if (evt.status === 'ok') {
          Tracks.done(evt.index, 'bypassed', evt.latency_ms || 0);
        }
        break;
      case 'analyzing':
        document.getElementById('live-phase').textContent = '信号提取中...';
        Log.add('信号提取 + 护栏检测...', 'info');
        break;
      case 'judging':
        document.getElementById('live-phase').textContent = '裁判判定中 (并行)...';
        Log.add('裁判并行判定中...', 'info');
        break;
      case 'judge_result':
        Tracks.done(evt.index, evt.verdict, evt.latency_ms || 0);
        break;
      case 'session_update':
        Sessions.update(evt.active_sessions, evt.killed_this_round);
        if (evt.killed_this_round && evt.killed_this_round.length) {
          Log.add('会话终止: ' + evt.killed_this_round.join(', '), 'warn');
        }
        break;
      case 'boundary_analysis':
        document.getElementById('live-phase').textContent = '边界分析中...';
        Log.add('分析失败响应 → 推测安全边界...', 'info');
        break;
      case 'kb5_updated':
        document.getElementById('kb5-bar').style.display = 'block';
        document.getElementById('kb5-text').textContent = evt.summary;
        Log.add('KB5 更新: ' + evt.summary.substring(0, 60) + '...', 'success');
        break;
      case 'info':
        Log.add(evt.message, 'info');
        break;
      case 'round_complete':
        App.allRounds.push(evt);
        renderRoundCard(evt);
        updateFinalSummary();
        var s = evt.summary || {};
        Log.add('轮次完成 — 绕过率 ' + (s.bypassRate || '0%') + ', 存活会话 ' + (s.activeSessions || 0), 'phase');
        document.getElementById('live-phase').textContent = '等待下一轮...';
        break;
      case 'stopped':
        document.getElementById('stop-reason-text').textContent = '终止: ' + evt.reason;
        Log.add('测试终止: ' + evt.reason, 'warn');
        if (typeof KB !== 'undefined' && KB.showKb5CleanupPrompt && buildConfig().agent3_enabled) {
          KB.showKb5CleanupPrompt();
          KB.refreshKb5State();
        }
        break;
      case 'error':
        Log.add((evt.round ? 'R' + evt.round + ': ' : '') + evt.message, 'error');
        toast(evt.message, 'error');
        finalize();
        break;
      case 'complete':
        updateFinalSummary();
        document.getElementById('live-phase').textContent = '测试完成';
        Log.add('测试完成 — 共 ' + evt.total_rounds + ' 轮, ' + evt.total_bypassed + ' 次绕过', 'phase');
        if (typeof KB !== 'undefined' && KB.showKb5CleanupPrompt && buildConfig().agent3_enabled) {
          KB.showKb5CleanupPrompt();
          KB.refreshKb5State();
        }
        finalize();
        break;
    }
  }
};

/* ── Utils ── */
function escHtml(s) { var d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }
function toggleRound(header) { var card = header.closest('.round-card'); var b = card.querySelector('.round-body'); var ch = card.querySelector('.chevron'); b.classList.toggle('open'); ch.classList.toggle('open'); }
function escLong(s, mx) {
  s = s || '';
  if (s.length <= mx) return escHtml(s);
  var id = 'xp' + Math.random().toFixed(6).slice(2);
  return '<span class="long-text collapsed" id="' + id + '"><span class="long-preview">' + escHtml(s.substring(0, mx)) + '</span><span class="long-full" style="display:none">' + escHtml(s) + '</span></span> <button class="btn btn-xs btn-ghost" data-toggle-long="' + id + '" data-full-len="' + s.length + '">展开 (' + s.length + '字)</button>';
}
document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-toggle-long]');
  if (!btn) return;
  var container = document.getElementById(btn.getAttribute('data-toggle-long'));
  if (!container) return;
  var full = container.querySelector('.long-full');
  var preview = container.querySelector('.long-preview');
  if (full.style.display === 'none') { full.style.display = 'inline'; preview.style.display = 'none'; btn.textContent = '收起'; }
  else { full.style.display = 'none'; preview.style.display = 'inline'; btn.textContent = '展开 (' + btn.getAttribute('data-full-len') + '字)'; }
});
function toast(msg, type) {
  var e = document.createElement('div'); e.className = 'toast ' + (type || 'info'); e.textContent = msg;
  document.body.appendChild(e);
  setTimeout(function () { e.style.opacity = '0'; e.style.transition = 'opacity .4s'; }, 3500);
  setTimeout(function () { e.remove(); }, 4000);
}

/* ── Password Toggle ── */
document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-toggle-pw]');
  if (!btn) return;
  var input = document.getElementById(btn.getAttribute('data-toggle-pw'));
  if (!input) return;
  if (input.type === 'password') { input.type = 'text'; btn.classList.add('active'); }
  else { input.type = 'password'; btn.classList.remove('active'); }
});

/* ── Theme ── */
function getTheme() { return localStorage.getItem(App.THEME_KEY) || 'dark'; }
function applyTheme(t) { document.body.classList.toggle('theme-light', t === 'light'); document.querySelector('.theme-toggle').innerHTML = t === 'light' ? '&#9788;' : '&#9790;'; localStorage.setItem(App.THEME_KEY, t); }
function toggleTheme() { applyTheme(getTheme() === 'dark' ? 'light' : 'dark'); }

/* ── Config Build ── */
function toggleCustomTemplate() {
  var isCustom = document.getElementById('template_name').value === 'custom';
  document.getElementById('custom-template-section').style.display = isCustom ? 'block' : 'none';
  document.getElementById('target-standard-fields').style.display = isCustom ? 'none' : '';
}

function toggleCustomSubMode() {
  var mode = document.getElementById('custom_sub_mode').value;
  document.getElementById('custom-simple-mode').style.display = mode === 'simple' ? 'block' : 'none';
  document.getElementById('custom-script-mode').style.display = mode === 'script' ? 'block' : 'none';
}

function toggleDualPacket() {
  var mode = document.getElementById('script_packet_mode').value;
  document.getElementById('dual-packet-section').style.display = mode === 'dual' ? 'block' : 'none';
}

function parseCurl() {
  var curlText = document.getElementById('curl_input').value.trim();
  var statusEl = document.getElementById('curl-parse-status');
  if (!curlText) { statusEl.textContent = '请先粘贴 curl 命令'; return; }
  statusEl.textContent = '解析中...';
  var payload = { curl: curlText, use_llm: true, agent_api_url: document.getElementById('agent_api_url').value.trim(), agent_api_key: document.getElementById('agent_api_key').value.trim(), agent_model: document.getElementById('agent_model').value.trim() || 'deepseek-chat' };
  fetch('/api/parse-curl', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.ok) { statusEl.textContent = d.error || '解析失败'; statusEl.style.color = 'var(--danger)'; return; }
      var cfg = d.data;
      document.getElementById('custom_method').value = cfg.method || 'POST';
      document.getElementById('custom_timeout').value = cfg.timeout || 120;
      document.getElementById('custom_headers').value = JSON.stringify(cfg.headers || {}, null, 2);
      document.getElementById('custom_body').value = JSON.stringify(cfg.body || {}, null, 2);
      document.getElementById('custom_content_path').value = (cfg.response_path || {}).content || '';
      document.getElementById('custom_reasoning_path').value = (cfg.response_path || {}).reasoning || '';
      document.getElementById('target_api_url').value = cfg.api_url || '';
      var method = cfg.prompt_slot_method || 'unknown';
      var label = method === 'rule' ? '规则匹配' : method === 'llm' ? 'LLM 辅助' : '需手动标注 {{prompt}}';
      statusEl.textContent = '解析完成 (' + label + ')';
      statusEl.style.color = method === 'manual' ? 'var(--warning)' : 'var(--success)';
    })
    .catch(function (e) { statusEl.textContent = '请求失败: ' + e.message; statusEl.style.color = 'var(--danger)'; });
}

/* ── 脚本模式 ── */
var _compiledScript = '';
var _scriptMode = 'single';

function compileScript() {
  var statusEl = document.getElementById('compile-status');
  var promptPacket = document.getElementById('script_prompt_packet').value.trim();
  if (!promptPacket) { statusEl.textContent = '请先粘贴提示词请求包'; statusEl.style.color = 'var(--danger)'; return; }

  var agentUrl = document.getElementById('agent_api_url').value.trim();
  var agentKey = document.getElementById('agent_api_key').value.trim();
  if (!agentUrl || !agentKey) { statusEl.textContent = '请先配置辅助模型'; statusEl.style.color = 'var(--danger)'; return; }

  statusEl.textContent = '编译中（LLM 生成脚本）...';
  statusEl.style.color = '';

  var payload = {
    prompt_packet: promptPacket,
    prompt_response: document.getElementById('script_prompt_response').value.trim(),
    session_packet: document.getElementById('script_session_packet') ? document.getElementById('script_session_packet').value.trim() : '',
    session_response: document.getElementById('script_session_response') ? document.getElementById('script_session_response').value.trim() : '',
    agent_api_url: agentUrl,
    agent_api_key: agentKey,
    agent_model: document.getElementById('agent_model').value.trim() || 'deepseek-chat'
  };

  fetch('/api/compile-script', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.ok) { statusEl.textContent = d.error || '编译失败'; statusEl.style.color = 'var(--danger)'; return; }
      _compiledScript = d.data.script;
      _scriptMode = d.data.mode;
      document.getElementById('script-preview').textContent = d.data.script;
      document.getElementById('script-preview-section').style.display = 'block';
      statusEl.textContent = '编译成功 (' + (d.data.mode === 'dual' ? '双流量包' : '单流量包') + ')';
      statusEl.style.color = 'var(--success)';
    })
    .catch(function (e) { statusEl.textContent = '请求失败: ' + e.message; statusEl.style.color = 'var(--danger)'; });
}

function confirmScript() {
  var el = document.getElementById('script-confirm-status');
  if (!_compiledScript) { el.textContent = '无脚本'; return; }
  el.textContent = '已确认，可开始测试';
  el.style.color = 'var(--success)';
}

function buildConfig() {
  var tn = document.getElementById('template_name').value;
  var cfg = {
    agent_api_url: document.getElementById('agent_api_url').value.trim(),
    agent_api_key: document.getElementById('agent_api_key').value.trim(),
    agent_model: document.getElementById('agent_model').value.trim() || 'deepseek-chat',
    target_api_url: document.getElementById('target_api_url').value.trim(),
    target_api_key: document.getElementById('target_api_key').value.trim(),
    target_model: document.getElementById('target_model').value.trim() || 'deepseek-chat',
    template_name: tn,
    max_rounds: parseInt(document.getElementById('max_rounds').value) || 5,
    cooldown_no_new: parseInt(document.getElementById('cooldown_no_new').value) || 2,
    allow_continuation: document.getElementById('allow_continuation').value === 'true',
    agent3_enabled: document.getElementById('agent3_enabled').value === 'true',
    agent2_enabled: document.getElementById('agent2_enabled').value === 'true',
    guardrail_keywords: document.getElementById('guardrail_keywords').value.trim()
  };
  var temperature = parseFloat(document.getElementById('target_temperature').value);
  if (!isNaN(temperature)) cfg.temperature = temperature;
  var topP = parseFloat(document.getElementById('target_top_p').value);
  if (!isNaN(topP)) cfg.top_p = topP;
  if (tn === 'custom') {
    var subMode = document.getElementById('custom_sub_mode').value;
    if (subMode === 'script' && _compiledScript) {
      cfg.compiled_script = _compiledScript;
      cfg.script_mode = _scriptMode;
    } else {
      cfg.method = document.getElementById('custom_method').value;
      cfg.timeout = parseInt(document.getElementById('custom_timeout').value) || 120;
      try { cfg.headers = JSON.parse(document.getElementById('custom_headers').value || '{}'); } catch (e) { cfg.headers = {}; }
      try { cfg.body = JSON.parse(document.getElementById('custom_body').value || '{}'); } catch (e) { cfg.body = {}; }
      cfg.response_path = { content: document.getElementById('custom_content_path').value.trim(), reasoning: document.getElementById('custom_reasoning_path').value.trim() };
      if (cfg.body && cfg.body.stream) cfg.stream = true;
    }
  }
  return cfg;
}

/* ── Test Control ── */
function probeTarget() {
  var s = document.getElementById('probe-status'); s.textContent = '检测中...';
  var cfg = buildConfig();
  if (cfg.compiled_script) {
    testFireScript(s);
    return;
  }
  var probeBody = { api_url: cfg.target_api_url, api_key: cfg.target_api_key, model: cfg.target_model, template_name: cfg.template_name, method: cfg.method, headers: cfg.headers, body: cfg.body };
  if (cfg.temperature !== undefined) probeBody.temperature = cfg.temperature;
  if (cfg.top_p !== undefined) probeBody.top_p = cfg.top_p;
  fetch('/api/probe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(probeBody) })
    .then(function (r) { return r.json(); })
    .then(function (d) { s.textContent = d.reachable ? '可达 (HTTP ' + d.status_code + ')' : (d.error || '不可达'); s.style.color = d.reachable ? 'var(--success)' : 'var(--danger)'; })
    .catch(function () { s.textContent = '请求失败'; s.style.color = 'var(--danger)'; });
}

function testFireScript(statusEl) {
  if (!_compiledScript) { statusEl.textContent = '请先编译脚本'; statusEl.style.color = 'var(--danger)'; return; }
  statusEl.textContent = '试射中（发送测试请求）...';
  var payload = {
    compiled_script: _compiledScript,
    script_mode: _scriptMode,
    test_prompt: '你好',
    agent_api_url: document.getElementById('agent_api_url').value.trim(),
    agent_api_key: document.getElementById('agent_api_key').value.trim(),
    agent_model: document.getElementById('agent_model').value.trim() || 'deepseek-chat'
  };
  fetch('/api/test-fire', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d.ok) { statusEl.textContent = '试射失败: ' + (d.error || '未知错误'); statusEl.style.color = 'var(--danger)'; return; }
      var r = d.data;
      if (r.response_text) {
        statusEl.textContent = '试射成功 (' + r.latency_ms + 'ms)';
        statusEl.style.color = 'var(--success)';
        document.getElementById('script-preview').textContent = _compiledScript + '\n\n/* ── 试射结果 ──\n响应: ' + r.response_text.substring(0, 200) + '\n*/';
      } else if (r.fix_applied) {
        _compiledScript = r.fixed_script;
        statusEl.textContent = '提取路径已修正，再次试射验证';
        statusEl.style.color = 'var(--warning)';
        document.getElementById('script-preview').textContent = r.fixed_script;
      } else {
        statusEl.textContent = '试射无响应: ' + (r.error || '提取路径可能有误');
        statusEl.style.color = 'var(--danger)';
        if (r.raw_response_sample) {
          document.getElementById('script-preview').textContent = _compiledScript + '\n\n/* ── 原始响应（提取失败）──\n' + r.raw_response_sample.substring(0, 500) + '\n*/';
        }
      }
    })
    .catch(function (e) { statusEl.textContent = '试射请求失败: ' + e.message; statusEl.style.color = 'var(--danger)'; });
}

function startTest() {
  var config = buildConfig();
  if (config.compiled_script) {
    // 脚本模式不需要 target_api_url/key
  } else if (!config.target_api_url || (!config.target_api_key && config.template_name !== 'custom')) {
    toast('请填写待测模型的 API 地址和 Key', 'error'); return;
  }
  App.allRounds = []; App.currentRound = 0;
  document.getElementById('rounds-container').innerHTML = '';
  document.getElementById('final-section').style.display = 'none';
  document.getElementById('progress-section').style.display = 'block';
  if (typeof KB !== 'undefined' && KB.hideKb5CleanupPrompt) {
    KB.hideKb5CleanupPrompt();
    var cleanupSection = document.getElementById('kb5-cleanup-actions');
    if (cleanupSection) cleanupSection.style.display = 'none';
  }
  document.getElementById('btn-start').disabled = true;
  document.getElementById('btn-stop').style.display = 'inline-flex';
  document.getElementById('stop-reason-text').textContent = '';
  Log.clear();
  Log.add('启动测试...', 'phase');
  document.getElementById('live-phase').textContent = '启动中...';
  App.elapsedStart = Date.now();
  App.elapsedTimer = setInterval(function () { document.getElementById('live-elapsed').textContent = ((Date.now() - App.elapsedStart) / 1000).toFixed(1) + 's'; }, 100);

  fetch('/api/test/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(config) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var data = d.data || d;
      if (data.error || d.error) { toast(data.error || d.error, 'error'); resetUI(); return; }
      App.taskId = data.task_id;
      EventBus.connect(App.taskId);
      EventBus.startPolling(App.taskId);
    })
    .catch(function (e) { toast('连接后端失败: ' + e.message, 'error'); resetUI(); });
}

function stopTest() {
  if (!App.taskId) return;
  fetch('/api/test/' + App.taskId + '/stop', { method: 'POST' }).catch(function () { /* fire-and-forget */ });
  Log.add('用户手动终止', 'warn');
  finalize();
}

function finalize() {
  document.getElementById('btn-start').disabled = false;
  document.getElementById('btn-stop').style.display = 'none';
  App.taskId = null;
  if (App.eventSource) { App.eventSource.close(); App.eventSource = null; }
  if (App.elapsedTimer) { clearInterval(App.elapsedTimer); App.elapsedTimer = null; }
  EventBus.stopPolling();
  if (typeof KB !== 'undefined' && KB.refreshKb5State) {
    KB.refreshKb5State();
  }
}
function resetUI() { document.getElementById('btn-start').disabled = false; document.getElementById('btn-stop').style.display = 'none'; }

/* ── Render ── */
function renderRoundCard(e) {
  var s = e.summary || {};
  var ns = e.nextStrategy || {};
  var ds = e.detailedResults || [];
  var ct = document.getElementById('rounds-container');
  var c = document.createElement('div'); c.className = 'round-card';

  var headerHtml = '<div class="round-header"><span class="round-title">R' + e.round + ' <span style="color:var(--accent)">' + escHtml(ns.primaryConcept || '') + '</span> / <span style="color:var(--purple)">' + escHtml(ns.primaryMethod || '') + '</span></span><span class="round-stats"><span>发送 <span class="round-stat-val">' + (s.total || 0) + '</span></span><span class="stat-success">绕过 <span class="round-stat-val">' + (s.bypassed || 0) + '</span></span><span class="stat-blocked">拒绝 <span class="round-stat-val">' + (s.blocked || 0) + '</span></span><span>' + (s.bypassRate || '0%') + '</span><span class="chevron">&#9660;</span></span></div>';

  var bodyHtml = '<div class="round-body"><div style="font-size:12px;color:var(--text-secondary);margin-bottom:8px">耗时 ' + (e.elapsed || '?') + 's | 新攻 ' + (s.newPrompts || 0) + ((s.contPrompts || 0) > 0 ? ' 续攻 ' + s.contPrompts : '') + ' | 存活 ' + (s.activeSessions || 0) + '</div>' + ds.map(renderDetailItem).join('') + (e.feedback ? '<div style="margin-top:10px;font-size:11px;color:var(--text-muted);border-top:1px solid var(--border-primary);padding-top:8px">' + escHtml(e.feedback) + '</div>' : '') + '</div>';

  c.innerHTML = headerHtml + bodyHtml;
  c.querySelector('.round-header').addEventListener('click', function () { var b = c.querySelector('.round-body'); var ch = c.querySelector('.chevron'); b.classList.toggle('open'); ch.classList.toggle('open'); });

  var prev = ct.querySelectorAll('.round-body.open');
  prev.forEach(function (p) { p.classList.remove('open'); });
  ct.querySelectorAll('.chevron.open').forEach(function (ch) { ch.classList.remove('open'); });

  ct.insertBefore(c, ct.firstChild);
  c.querySelector('.round-body').classList.add('open');
  c.querySelector('.chevron').classList.add('open');
}

function renderDetailItem(d) {
  var sm = { bypassed: { cls: 'bypassed', text: '绕过', badge: 'badge-bypass' }, blocked: { cls: 'blocked', text: '拒绝', badge: 'badge-block' }, partial: { cls: 'partial', text: '部分', badge: 'badge-partial' }, guardrail_blocked: { cls: 'blocked', text: '护栏', badge: 'badge-guardrail' }, error: { cls: 'blocked', text: '错误', badge: 'badge-error' } };
  var info = sm[d.jailbreakStatus] || sm['partial'];
  var typeTag = d.promptType === 'continue' ? '<span class="badge badge-continue">续攻·' + escHtml(d.sessionId || '') + '</span>' : '';
  var errorLine = d.error ? '<div class="result-text" style="margin-top:6px;color:#e74c3c"><span class="label-text">Error</span><br>' + escHtml(d.error) + '</div>' : '';
  return '<div class="result-item ' + info.cls + '"><div class="result-meta"><span class="badge ' + info.badge + '">' + info.text + '</span>' + typeTag + '<span class="badge badge-concept">' + escHtml(d.concept || '') + '</span><span>' + (d.latencyMs || 0) + 'ms</span>' + (d.judge_reason ? '<span title="' + escHtml(d.judge_reason) + '">裁判</span>' : '') + '</div><div class="result-text"><span class="label-text">Prompt</span><br>' + escLong(d.promptText || '', 300) + '</div><div class="result-text" style="margin-top:6px"><span class="label-text">Response</span><br>' + escLong(d.modelResponse || '', 400) + '</div>' + errorLine + '</div>';
}

function updateFinalSummary() {
  document.getElementById('final-section').style.display = 'block';
  document.getElementById('sum-cycles').textContent = App.allRounds.length;
  var ts = 0, br = 0, rates = [];
  App.allRounds.forEach(function (r) { var s = r.summary || {}; ts += s.bypassed || 0; var rt = parseFloat((s.bypassRate || '0').replace('%', '')); rates.push(rt); if (rt > br) br = rt; });
  var cv = new Set();
  App.allRounds.forEach(function (r) { (r.detailedResults || []).forEach(function (d) { if (d.jailbreakStatus === 'bypassed' && d.category) cv.add(d.category); }); });
  document.getElementById('sum-success').textContent = ts;
  document.getElementById('sum-coverage').textContent = cv.size + '/31';
  document.getElementById('sum-peak').textContent = br.toFixed(0) + '%';
  var mx = Math.max.apply(null, rates.concat([1]));
  document.getElementById('chart-bypass').innerHTML = rates.map(function (r, i) { return '<div class="bar-col"><div class="bar-fill" style="height:' + (r / mx * 100).toFixed(0) + '%"></div><div class="bar-label">R' + (i + 1) + '</div></div>'; }).join('');
  document.getElementById('chart-covered').innerHTML = cv.size > 0 ? '<div class="kb-list">' + Array.from(cv).sort().map(function (c) { return '<span class="kb-tag">' + c + '</span>'; }).join('') + '</div>' : '暂无';
}

/* ── Init ── */
document.addEventListener('DOMContentLoaded', function () {
  applyTheme(getTheme());
  document.querySelectorAll('.nav-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.nav-tab').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.nav-panel').forEach(function (p) { p.style.display = 'none'; });
      btn.classList.add('active');
      var panel = document.getElementById(btn.dataset.nav);
      if (panel) panel.style.display = 'block';
      if (btn.dataset.nav === 'nav-sessions' && typeof Sessions !== 'undefined' && Sessions.load) Sessions.load();
      if (btn.dataset.nav === 'nav-kb' && typeof KB !== 'undefined') KB.switchKb('kb1');
    });
  });
  document.querySelectorAll('.tab-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var parent = btn.closest('.card');
      parent.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
      parent.querySelectorAll('.tab-panel').forEach(function (p) { p.classList.remove('active'); });
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
    });
  });
  document.querySelector('.theme-toggle').addEventListener('click', toggleTheme);
  document.getElementById('btn-start').addEventListener('click', startTest);
  document.getElementById('btn-stop').addEventListener('click', stopTest);
  document.querySelector('[data-action="probe"]').addEventListener('click', probeTarget);
  document.getElementById('template_name').addEventListener('change', toggleCustomTemplate);
  document.getElementById('btn-parse-curl').addEventListener('click', parseCurl);
  var compileBtn = document.getElementById('btn-compile-script');
  if (compileBtn) compileBtn.addEventListener('click', compileScript);
  var confirmBtn = document.getElementById('btn-confirm-script');
  if (confirmBtn) confirmBtn.addEventListener('click', confirmScript);
  document.getElementById('btn-load-claude-cfg').addEventListener('click', loadClaudeCfg);
  document.getElementById('btn-save-claude-cfg').addEventListener('click', saveClaudeCfg);
  document.getElementById('btn-sync-aux').addEventListener('click', syncToAux);
  loadClaudeCfg();
  if (document.getElementById('kb-add-btn')) document.getElementById('kb-add-btn').addEventListener('click', function () { if (typeof KB !== 'undefined') KB.addEntry(); });
});

function loadClaudeCfg() {
  fetch('/api/claude-agent/config').then(function (r) { return r.json(); }).then(function (d) {
    var data = d.data || {};
    var status = data.status || {};
    document.getElementById('claude_agent_url').value = data.url || '';
    document.getElementById('claude_agent_key').value = data.key || '';
    document.getElementById('claude_agent_model').value = data.model || '';
    var st = document.getElementById('claude-cfg-status');
    if (st) {
      st.textContent = status.message || '';
      st.style.color = status.ready ? 'var(--success)' : 'var(--warning)';
    }
  }).catch(function () { toast('加载提示词生成配置失败', 'error'); });
}
function saveClaudeCfg() {
  var payload = { url: document.getElementById('claude_agent_url').value.trim(), key: document.getElementById('claude_agent_key').value.trim(), model: document.getElementById('claude_agent_model').value.trim() };
  fetch('/api/claude-agent/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      var st = document.getElementById('claude-cfg-status');
      st.textContent = d.ok ? '已保存' : (d.error || '失败');
      setTimeout(function () { loadClaudeCfg(); }, 100);
    })
    .catch(function () { toast('保存配置失败', 'error'); });
}
function syncToAux() {
  var url = document.getElementById('claude_agent_url').value.trim();
  var key = document.getElementById('claude_agent_key').value.trim();
  var model = document.getElementById('claude_agent_model').value.trim();
  if (!url && !key) { toast('提示词生成配置为空，无法同步', 'error'); return; }
  url = url.replace(/\/anthropic\/?$/, '');
  document.getElementById('agent_api_url').value = url;
  document.getElementById('agent_api_key').value = key;
  document.getElementById('agent_model').value = model;
  toast('已同步到辅助模型', 'success');
}
