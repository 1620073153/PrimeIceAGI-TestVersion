/**
 * PrimeIceAGI — 主应用逻辑
 * App 命名空间 + EventBus + 核心测试流程
 */
'use strict';

/* ================================================================
   App 命名空间 — 收束所有全局状态
   ================================================================ */
var App = {
  taskId: null,
  eventSource: null,
  allRounds: [],
  currentRound: 0,
  pollTimer: null,
  singleDoneCount: 0,
  generatingTimer: null,
  generatingElapsed: 0,
  THEME_KEY: 'primeiceagi-theme',

  maxRounds: function () {
    return parseInt(document.getElementById('max_rounds').value) || 5;
  }
};

/* ================================================================
   EventBus — SSE / 轮询封装
   ================================================================ */
var EventBus = {
  connect: function (taskId) {
    if (App.eventSource) App.eventSource.close();
    App.eventSource = new EventSource('/api/test/' + taskId + '/stream');
    App.eventSource.onmessage = function (e) {
      EventBus.handleEvent(JSON.parse(e.data));
    };
    App.eventSource.onerror = function () {
      if (!App.taskId) App.eventSource.close();
    };
  },

  startPolling: function (tid) {
    EventBus.stopPolling();
    App.pollTimer = setInterval(function () {
      fetch('/api/test/' + tid + '/status')
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (d.finished && d.report) {
            EventBus.stopPolling();
            if (App.taskId === tid) {
              var rp = d.report;
              App.allRounds = rp.rounds || [];
              document.getElementById('rounds-container').innerHTML = '';
              for (var i = 0; i < App.allRounds.length; i++) {
                renderRoundCard(App.allRounds[i]);
              }
              updateFinalSummary();
              document.getElementById('progress-bar').style.width = '100%';
              document.getElementById('progress-title').textContent = '测试完成（轮询恢复）';
              document.getElementById('progress-round').textContent = '共 ' + rp.total_rounds + ' 轮, ' + rp.total_bypassed + ' 次成功绕过';
              DAG.setAll('done');
              finalize();
            }
          }
        })
        .catch(function () {});
    }, 3000);
  },

  stopPolling: function () {
    if (App.pollTimer) {
      clearInterval(App.pollTimer);
      App.pollTimer = null;
    }
  },

  handleEvent: function (evt) {
    switch (evt.event) {
      case 'round_start':
        App.currentRound = evt.round;
        App.singleDoneCount = 0;
        App.generatingElapsed = 0;
        if (App.generatingTimer) { clearInterval(App.generatingTimer); App.generatingTimer = null; }
        document.getElementById('progress-round').textContent = '第 ' + evt.round + '/' + evt.total_rounds + ' 轮 — 提示词生成中...';
        document.getElementById('progress-bar').style.width = ((evt.round - 1) / App.maxRounds() * 100) + '%';
        DAG.setAll('waiting');
        DAG.setNode('agent1', 'active');
        break;
      case 'generating':
        DAG.setNode('agent1', 'active');
        App.generatingElapsed = 0;
        if (App.generatingTimer) clearInterval(App.generatingTimer);
        App.generatingTimer = setInterval(function () {
          App.generatingElapsed++;
          document.getElementById('progress-round').textContent = '第 ' + App.currentRound + '/' + App.maxRounds() + ' 轮 — 提示词生成中 (已等待 ' + App.generatingElapsed + 's，大模型推理需要时间)';
        }, 1000);
        document.getElementById('progress-round').textContent = '第 ' + App.currentRound + '/' + App.maxRounds() + ' 轮 — 提示词生成中 (已等待 0s，大模型推理需要时间)';
        break;
      case 'testing':
        if (App.generatingTimer) { clearInterval(App.generatingTimer); App.generatingTimer = null; }
        App.singleDoneCount = 0;
        document.getElementById('progress-round').textContent = '第 ' + evt.round + ' 轮 — 并行调用待测模型 (' + (evt.count || 10) + ' 条)...';
        DAG.setNode('agent1', 'done');
        DAG.setNode('parallel', 'active');
        break;
      case 'single_done':
        App.singleDoneCount++;
        document.getElementById('progress-round').textContent = '第 ' + App.currentRound + ' 轮 — 并行调用 (' + App.singleDoneCount + '/' + (evt.total || 10) + ' 完成)';
        break;
      case 'analyzing':
        document.getElementById('progress-round').textContent = '第 ' + evt.round + ' 轮 — 信号提取中...';
        DAG.setNode('parallel', 'done');
        DAG.setNode('signal', 'active');
        break;
      case 'judging':
        document.getElementById('progress-round').textContent = '第 ' + evt.round + ' 轮 — Agent2 响应裁判中...';
        DAG.setNode('signal', 'done');
        DAG.setNode('judge', 'active');
        break;
      case 'deepening':
        document.getElementById('progress-round').textContent = '第 ' + evt.round + ' 轮 — 启动 ' + (evt.sessions || 0) + ' 个多轮深挖会话...';
        DAG.setNode('judge', 'done');
        DAG.setNode('deepener', 'active');
        break;
      case 'deepener_done':
        break;
      case 'round_complete':
        App.allRounds.push(evt);
        renderRoundCard(evt);
        updateProgress(evt);
        updateFinalSummary();
        DAG.setAll('done');
        break;
      case 'stopped':
        document.getElementById('stop-reason-text').textContent = '终止原因: ' + evt.reason;
        break;
      case 'error':
        toast((evt.round ? '第' + evt.round + '轮: ' : '') + evt.message, 'error');
        DAG.NODES.forEach(function (n) {
          var el = document.querySelector('.dag-node[data-node="' + n + '"]');
          if (el && el.classList.contains('active')) DAG.setNode(n, 'error');
        });
        DAG.setNode('arbitrator', 'error');
        finalize();
        break;
      case 'complete':
        if (App.generatingTimer) { clearInterval(App.generatingTimer); App.generatingTimer = null; }
        updateFinalSummary();
        document.getElementById('progress-bar').style.width = '100%';
        document.getElementById('progress-title').textContent = '测试完成';
        document.getElementById('progress-round').textContent = '共 ' + evt.total_rounds + ' 轮, ' + evt.total_bypassed + ' 次成功绕过';
        DAG.setAll('done');
        finalize();
        var finalEl = document.getElementById('final-section');
        if (finalEl) finalEl.scrollIntoView({ behavior: 'smooth' });
        break;
    }
  }
};

/* ================================================================
   工具函数
   ================================================================ */
function escHtml(s) {
  var d = document.createElement('div');
  d.textContent = (s || '');
  return d.innerHTML;
}

function escLong(s, mx) {
  s = s || '';
  if (s.length <= mx) return escHtml(s);
  var id = 'xp' + Math.random().toFixed(6).slice(2);
  return '<span class="long-text collapsed" id="' + id + '">'
    + '<span class="long-preview">' + escHtml(s.substring(0, mx)) + '</span>'
    + '<span class="long-full" style="display:none">' + escHtml(s) + '</span>'
    + '</span> <button class="btn btn-xs btn-ghost" style="vertical-align:baseline" data-toggle-long="' + id + '" data-full-len="' + s.length + '">展开全部 (' + s.length + '字)</button>';
}

// 事件委托：处理 escLong 生成的展开/收起按钮点击（替代 inline onclick，消除 XSS 隐患）
document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-toggle-long]');
  if (!btn) return;
  var id = btn.getAttribute('data-toggle-long');
  var container = document.getElementById(id);
  if (!container) return;
  var full = container.querySelector('.long-full');
  var preview = container.querySelector('.long-preview');
  container.classList.toggle('collapsed');
  if (full.style.display === 'none') {
    full.style.display = 'inline';
    preview.style.display = 'none';
    btn.textContent = '收起';
  } else {
    full.style.display = 'none';
    preview.style.display = 'inline';
    btn.textContent = '展开全部 (' + btn.getAttribute('data-full-len') + '字)';
  }
});
function toast(msg, type) {
  var e = document.createElement('div');
  e.className = 'toast ' + type;
  e.textContent = msg;
  document.body.appendChild(e);
  setTimeout(function () {
    e.style.opacity = '0';
    e.style.transition = 'opacity .4s';
  }, 3500);
  setTimeout(function () { e.remove(); }, 4000);
}

/* ================================================================
   主题切换
   ================================================================ */
function getTheme() { return localStorage.getItem(App.THEME_KEY) || 'dark'; }

function applyTheme(t) {
  document.body.classList.toggle('theme-light', t === 'light');
  document.querySelector('.theme-toggle').innerHTML = t === 'light' ? '&#9788;' : '&#9790;';
  localStorage.setItem(App.THEME_KEY, t);
}

function toggleTheme() { applyTheme(getTheme() === 'dark' ? 'light' : 'dark'); }

/* ================================================================
   配置构建
   ================================================================ */
function toggleCustomTemplate() {
  document.getElementById('custom-template-section').style.display =
    document.getElementById('template_name').value === 'custom' ? 'block' : 'none';
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
    deepener_enabled: document.getElementById('deepener_enabled').value === 'true',
    deepener_max_turns: parseInt(document.getElementById('deepener_max_turns').value) || 5,
    agent3_enabled: document.getElementById('agent3_enabled').value === 'true',
    agent2_enabled: document.getElementById('agent2_enabled').value === 'true',
    guardrail_keywords: document.getElementById('guardrail_keywords').value.trim()
  };
  if (tn === 'custom') {
    cfg.method = document.getElementById('custom_method').value;
    cfg.timeout = parseInt(document.getElementById('custom_timeout').value) || 120;
    try { cfg.headers = JSON.parse(document.getElementById('custom_headers').value || '{}'); } catch (e) { cfg.headers = {}; }
    try { cfg.body = JSON.parse(document.getElementById('custom_body').value || '{}'); } catch (e) { cfg.body = {}; }
    cfg.response_path = {
      content: document.getElementById('custom_content_path').value.trim(),
      reasoning: document.getElementById('custom_reasoning_path').value.trim()
    };
  }
  return cfg;
}
/* ================================================================
   测试控制
   ================================================================ */
function probeTarget() {
  var s = document.getElementById('probe-status');
  s.textContent = '检测中...';
  s.style.color = 'var(--text-secondary)';
  var cfg = buildConfig();
  fetch('/api/probe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_url: cfg.target_api_url, api_key: cfg.target_api_key,
      model: cfg.target_model, template_name: cfg.template_name,
      method: cfg.method, headers: cfg.headers, body: cfg.body
    })
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.reachable) {
        s.textContent = '✓ 可达 (HTTP ' + d.status_code + ')';
        s.style.color = 'var(--success-emerald)';
      } else {
        s.textContent = '✗ ' + (d.error || '不可达');
        s.style.color = 'var(--danger-coral)';
      }
    })
    .catch(function () {
      s.textContent = '✗ 请求失败';
      s.style.color = 'var(--danger-coral)';
    });
}

function startTest() {
  var config = buildConfig();
  if (!config.agent_api_url || !config.agent_api_key || !config.target_api_url || !config.target_api_key) {
    toast('请填写所有必填字段', 'error');
    return;
  }
  App.allRounds = [];
  App.currentRound = 0;
  document.getElementById('rounds-container').innerHTML = '';
  document.getElementById('final-section').style.display = 'none';
  document.getElementById('progress-section').style.display = 'block';
  document.getElementById('progress-title').textContent = '测试进行中...';
  document.getElementById('progress-bar').style.width = '0%';
  document.getElementById('progress-round').textContent = '启动中...';
  document.getElementById('progress-bypass').textContent = '';
  document.getElementById('btn-start').disabled = true;
  document.getElementById('btn-stop').style.display = 'inline-flex';
  document.getElementById('stop-reason-text').textContent = '';
  DAG.setAll('waiting');
  DAG.setNode('agent1', 'active');
  DAG.startMonitor();

  fetch('/api/test/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.error) { toast(d.error, 'error'); resetUI(); return; }
      App.taskId = d.task_id;
      EventBus.connect(App.taskId);
      EventBus.startPolling(App.taskId);
    })
    .catch(function (e) {
      toast('无法连接后端: ' + e.message, 'error');
      resetUI();
    });
}

function stopTest() {
  if (!App.taskId) return;
  fetch('/api/test/' + App.taskId + '/stop', { method: 'POST' }).catch(function () {});
  document.getElementById('stop-reason-text').textContent = '用户手动终止';
  finalize();
}

function finalize() {
  document.getElementById('btn-start').disabled = false;
  document.getElementById('btn-stop').style.display = 'none';
  App.taskId = null;
  if (App.eventSource) { App.eventSource.close(); App.eventSource = null; }
  if (App.generatingTimer) { clearInterval(App.generatingTimer); App.generatingTimer = null; }
  DAG.stopMonitor();
  EventBus.stopPolling();
}

function resetUI() {
  document.getElementById('btn-start').disabled = false;
  document.getElementById('btn-stop').style.display = 'none';
}
/* ================================================================
   进度 & 结果渲染
   ================================================================ */
function updateProgress(e) {
  var s = e.summary || {};
  document.getElementById('progress-bar').style.width = (App.currentRound / App.maxRounds() * 100) + '%';
  document.getElementById('progress-bypass').textContent = '本轮绕过率: ' + (s.bypassRate || '0%');
}

function renderRoundCard(e) {
  var s = e.summary || {};
  var ns = e.nextStrategy || {};
  var ds = e.detailedResults || [];
  var ct = document.getElementById('rounds-container');

  var c = document.createElement('div');
  c.className = 'round-card';
  c.id = 'round-' + e.round;

  var guardrailHtml = (s.guardrailBlocked > 0) ? '<span style="color:var(--text-muted)">护栏 <span class="round-stat-val">' + s.guardrailBlocked + '</span></span>' : '';
  var headerHtml = '<div class="round-header"><span class="round-title">第 ' + e.round + ' 轮 &middot; <span style="color:var(--accent-cyan)">' + escHtml(ns.primaryConcept || '—') + '</span> / <span style="color:var(--accent-purple)">' + escHtml(ns.primaryMethod || '—') + '</span>' + (ns.variantMode ? ' <span style="color:var(--warn-amber);font-size:.68rem">[以点打面]</span>' : '') + '</span><span class="round-stats"><span>发送 <span class="round-stat-val">' + (s.total || 0) + '</span></span><span class="stat-success">成功 <span class="round-stat-val">' + (s.bypassed || 0) + '</span></span><span class="stat-partial">部分 <span class="round-stat-val">' + (s.partial || 0) + '</span></span><span class="stat-blocked">拒绝 <span class="round-stat-val">' + (s.blocked || 0) + '</span></span>' + guardrailHtml + (s.deepSessions > 0 ? '<span style="color:var(--accent-purple)">深挖 <span class="round-stat-val">' + (s.deepBypassed || 0) + '</span></span>' : '') + '<span style="color:var(--text-secondary)">' + (s.bypassRate || '0%') + '</span><span class="chevron">&#9660;</span></span></div>';

  var bodyHtml = '<div class="round-body"><div style="font-size:.78rem;color:var(--text-secondary);margin-top:10px">主信号: <b style="color:var(--accent-cyan)">' + escHtml(s.primarySignal || '—') + '</b> &middot; 耗时: ' + (e.elapsed || '?') + 's &middot; 下轮目标: ' + ((ns.subcategories || []).slice(0, 3).join(', ') || '—') + '</div>' + ds.map(renderDetailItem).join('') + (e.feedback ? '<div style="margin-top:10px;font-size:.74rem;color:var(--text-muted);border-top:1px solid var(--glass-border);padding-top:10px">' + escHtml(e.feedback) + '</div>' : '') + '</div>';

  c.innerHTML = headerHtml + bodyHtml;

  // Attach event listener to header instead of inline onclick
  var header = c.querySelector('.round-header');
  header.addEventListener('click', function () { toggleRound(header); });

  // Collapse all previous round cards before inserting new one
  var existingBodies = ct.querySelectorAll('.round-body.open');
  var existingChevrons = ct.querySelectorAll('.chevron.open');
  for (var i = 0; i < existingBodies.length; i++) existingBodies[i].classList.remove('open');
  for (var i = 0; i < existingChevrons.length; i++) existingChevrons[i].classList.remove('open');

  ct.insertBefore(c, ct.firstChild);
  c.querySelector('.round-body').classList.add('open');
  c.querySelector('.chevron').classList.add('open');
}

function renderDetailItem(d) {
  var statusMap = {
    'bypassed': {cls: 'bypassed', text: '越狱成功', badge: 'badge-bypass'},
    'blocked': {cls: 'blocked', text: '被拒绝', badge: 'badge-block'},
    'partial': {cls: 'partial', text: '部分突破', badge: 'badge-partial'},
    'guardrail_blocked': {cls: 'blocked', text: '护栏拦截', badge: 'badge-guardrail'}
  };
  var info = statusMap[d.jailbreakStatus] || statusMap['partial'];
  var cls = info.cls;
  var bTxt = info.text;
  var bCls = info.badge;
  var dt = d.deepenerTurns || [];
  var dh = '';

  if (dt.length > 0) {
    var dbp = dt.filter(function (t) { return t.jailbreakStatus === 'bypassed'; }).length;
    var deepStatusMap = {
      'bypassed': {cls: 'bypassed', text: '突破', badge: 'badge-bypass'},
      'blocked': {cls: 'blocked', text: '拒绝', badge: 'badge-block'},
      'partial': {cls: 'partial', text: '部分', badge: 'badge-partial'},
      'guardrail_blocked': {cls: 'blocked', text: '护栏拦截', badge: 'badge-guardrail'}
    };
    dh = '<div style="margin-top:8px;border-top:1px dashed var(--glass-border);padding-top:8px"><div style="font-size:.72rem;color:var(--accent-purple);font-weight:600;margin-bottom:6px">↳ 多轮深挖 (' + dt.length + ' 轮追问, ' + dbp + ' 次继续成功)</div>' + dt.map(function (t) {
      var ti = deepStatusMap[t.jailbreakStatus] || deepStatusMap['partial'];
      return '<div class="result-item ' + ti.cls + '" style="margin-top:4px;padding:10px 12px"><div class="result-meta"><span class="badge ' + ti.badge + '">' + ti.text + '</span><span>第' + t.turn + '轮追问</span><span>信号: ' + escHtml((t.signals || []).join(', ') || '无') + '</span>' + (t.sessionEnded ? ' <span style="color:var(--danger-coral);font-size:.62rem">[' + (t.endReason || '终止') + ']</span>' : '') + '</div><div class="result-text"><span class="label-text">追问</span><br>' + escLong((t.prompt_text || ''), 250) + '</div><div class="result-text" style="margin-top:5px"><span class="label-text">回复</span><br>' + escLong((t.response_text || ''), 300) + '</div></div>';
    }).join('') + '</div>';
  }

  var judgeInfo = d.judge_reason ? '<span style="font-size:.62rem;color:var(--text-muted)" title="' + escHtml(d.judge_reason) + '">裁判</span>' : '';
  return '<div class="result-item ' + cls + '"><div class="result-meta"><span class="badge ' + bCls + '">' + bTxt + '</span><span class="badge badge-concept">' + escHtml(d.concept || '') + '</span><span class="badge badge-method">' + escHtml(d.method || '') + '</span>' + judgeInfo + '<span>信号: ' + escHtml((d.signals || []).join(', ') || '无') + '</span><span>延迟: ' + (d.latencyMs || 0) + 'ms</span>' + (dt.length > 0 ? '<span style="color:var(--accent-purple)">深挖: ' + dt.length + '轮</span>' : '') + '</div><div class="result-text"><span class="label-text">初始提示词</span><br>' + escLong((d.promptText || ''), 300) + '</div><div class="result-text" style="margin-top:6px"><span class="label-text">初始响应</span><br>' + escLong((d.modelResponse || ''), 400) + '</div>' + dh + '</div>';
}

function updateFinalSummary() {
  document.getElementById('final-section').style.display = 'block';
  document.getElementById('sum-cycles').textContent = App.allRounds.length;
  var ts = 0, br = 0;
  var rates = [];
  for (var i = 0; i < App.allRounds.length; i++) {
    var s = App.allRounds[i].summary || {};
    ts += s.bypassed || 0;
    var rt = parseFloat((s.bypassRate || '0').replace('%', ''));
    rates.push(rt);
    if (rt > br) br = rt;
  }
  var cv = new Set();
  for (var i = 0; i < App.allRounds.length; i++) {
    var ds = App.allRounds[i].detailedResults || [];
    for (var j = 0; j < ds.length; j++) {
      if (ds[j].jailbreakStatus === 'bypassed' && ds[j].category) cv.add(ds[j].category);
    }
  }
  document.getElementById('sum-success').textContent = ts;
  document.getElementById('sum-coverage').textContent = cv.size + '/31';
  document.getElementById('sum-peak').textContent = br.toFixed(0) + '%';
  var mx = Math.max.apply(null, rates.concat([1]));
  document.getElementById('chart-bypass').innerHTML = rates.map(function (r, i) {
    return '<div class="bar-col"><div class="bar-fill" style="height:' + (r / mx * 100).toFixed(0) + '%"></div><div class="bar-label">R' + (i + 1) + '<br>' + r.toFixed(0) + '%</div></div>';
  }).join('');
  document.getElementById('chart-covered').innerHTML = cv.size > 0 ? '<div class="kb-list">' + Array.from(cv).sort().map(function (c) { return '<span class="kb-tag">' + c + '</span>'; }).join('') + '</div>' : '暂无成功绕过';
}

function toggleRound(h) {
  var b = h.nextElementSibling;
  var c = h.querySelector('.chevron');
  b.classList.toggle('open');
  c.classList.toggle('open');
}

/* ================================================================
   导航 & Tab 初始化
   ================================================================ */
document.addEventListener('DOMContentLoaded', function () {
  // 主题
  applyTheme(getTheme());

  // 导航 tabs
  document.querySelectorAll('.nav-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.nav-tab').forEach(function (b) { b.classList.remove('active'); });
      document.querySelectorAll('.nav-panel').forEach(function (p) { p.style.display = 'none'; });
      btn.classList.add('active');
      var panel = document.getElementById(btn.dataset.nav);
      if (panel) panel.style.display = 'block';
      if (btn.dataset.nav === 'nav-sessions') Sessions.load();
      if (btn.dataset.nav === 'nav-kb') KB.switchKb('kb1');
    });
  });

  // 内部 tabs
  document.querySelectorAll('.tab-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var parent = btn.closest('.card');
      parent.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
      parent.querySelectorAll('.tab-panel').forEach(function (p) { p.classList.remove('active'); });
      btn.classList.add('active');
      document.getElementById(btn.dataset.tab).classList.add('active');
    });
  });

  // 主题切换按钮
  document.querySelector('.theme-toggle').addEventListener('click', toggleTheme);

  // 测试按钮
  document.getElementById('btn-start').addEventListener('click', startTest);
  document.getElementById('btn-stop').addEventListener('click', stopTest);

  // 连通性检测
  document.querySelector('[data-action="probe"]').addEventListener('click', probeTarget);

  // 模板切换
  document.getElementById('template_name').addEventListener('change', toggleCustomTemplate);

  // KB add 按钮
  document.getElementById('kb-add-btn').addEventListener('click', function () { KB.addEntry(); });
});
