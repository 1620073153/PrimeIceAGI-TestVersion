/**
 * PrimeIceAGI — 历史会话模块
 * 会话列表加载、详情展开、报告查看、删除
 */
'use strict';

var Sessions = {
  load: function () {
    var ct = document.getElementById('sessions-list');
    fetch('/api/sessions')
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var payload = d.data || d;
        var ss = payload.sessions || [];
        if (ss.length === 0) {
          ct.innerHTML = '<div style="color:var(--text-muted);font-size:.82rem">暂无历史会话</div>';
          return;
        }
        ct.innerHTML = '';
        ss.forEach(function (s) {
          var card = document.createElement('div');
          card.className = 'session-card';
          card.id = 'sess-' + s.session_id;

          var metaDiv = document.createElement('div');
          metaDiv.className = 'session-meta';

          var left = document.createElement('div');
          var titleDiv = document.createElement('div');
          titleDiv.className = 'session-title';
          titleDiv.textContent = new Date((s.created_at || 0) * 1000).toLocaleString('zh-CN');
          var statsDiv = document.createElement('div');
          statsDiv.className = 'session-stats';
          statsDiv.textContent = 'Agent: ' + (s.config && s.config.agent_model || '—') + ' | Target: ' + (s.config && s.config.target_model || '—');
          left.appendChild(titleDiv);
          left.appendChild(statsDiv);

          var right = document.createElement('div');
          right.className = 'session-stats';
          right.textContent = s.total_rounds + '轮 | 绕过' + s.total_bypassed + ' | ' + s.coverage_rate + ' | 峰值' + s.best_bypass_rate;

          metaDiv.appendChild(left);
          metaDiv.appendChild(right);
          metaDiv.addEventListener('click', (function (sid) {
            return function () { Sessions.toggleDetail(sid); };
          })(s.session_id));

          var detail = document.createElement('div');
          detail.className = 'session-detail';
          detail.id = 'sess-detail-' + s.session_id;
          var btnRow = document.createElement('div');
          btnRow.style.cssText = 'display:flex;gap:8px;margin-bottom:10px';

          var viewBtn = document.createElement('button');
          viewBtn.className = 'btn btn-ghost btn-xs';
          viewBtn.textContent = '查看完整报告';
          viewBtn.addEventListener('click', (function (sid) {
            return function () { Sessions.loadReport(sid); };
          })(s.session_id));

          var delBtn = document.createElement('button');
          delBtn.className = 'btn btn-ghost btn-xs';
          delBtn.style.color = 'var(--danger)';
          delBtn.textContent = '删除';
          delBtn.addEventListener('click', (function (sid) {
            return function () { Sessions.deleteSession(sid); };
          })(s.session_id));

          btnRow.appendChild(viewBtn);
          btnRow.appendChild(delBtn);
          detail.appendChild(btnRow);

          var reportDiv = document.createElement('div');
          reportDiv.className = 'session-rounds';
          reportDiv.id = 'sess-report-' + s.session_id;
          detail.appendChild(reportDiv);

          card.appendChild(metaDiv);
          card.appendChild(detail);
          ct.appendChild(card);
        });
      })
      .catch(function (e) { ct.innerHTML = '加载失败: ' + e.message; });
  },

  toggleDetail: function (sid) {
    document.getElementById('sess-detail-' + sid).classList.toggle('open');
  },

  loadReport: function (sid) {
    var ct = document.getElementById('sess-report-' + sid);
    ct.innerHTML = '加载中...';
    fetch('/api/sessions/' + sid)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var payload = d.data || d;
        var rp = payload.report || {};
        var rs = rp.rounds || [];
        if (rs.length === 0) {
          ct.innerHTML = '<div style="color:var(--text-muted);font-size:.76rem">无轮次数据</div>';
          return;
        }
        ct.innerHTML = '';
        rs.forEach(function (rd) {
          var s = rd.summary || {};
          var ns = rd.nextStrategy || {};
          var ds = rd.detailedResults || [];

          var roundCard = document.createElement('div');
          roundCard.className = 'round-card';
          roundCard.style.marginBottom = '12px';

          var headerHtml = '<div class="round-header"><span class="round-title">第' + rd.round + '轮 &middot; <span style="color:var(--accent)">' + escHtml(ns.primaryConcept || '?') + '</span> / <span style="color:var(--purple)">' + escHtml(ns.primaryMethod || '?') + '</span></span><span class="round-stats"><span>发送 <span class="round-stat-val">' + (s.total || 0) + '</span></span><span class="stat-success">成功 <span class="round-stat-val">' + (s.bypassed || 0) + '</span></span><span class="stat-blocked">拒绝 <span class="round-stat-val">' + (s.blocked || 0) + '</span></span><span style="color:var(--text-secondary)">' + (s.bypassRate || '0%') + '</span><span class="chevron">&#9660;</span></span></div>';

          var bodyHtml = '<div class="round-body"><div style="font-size:.78rem;color:var(--text-secondary);margin-top:10px">主信号: <b style="color:var(--accent)">' + escHtml(s.primarySignal || '—') + '</b> &middot; 耗时: ' + (rd.elapsed || '?') + 's &middot; 下轮目标: ' + ((ns.subcategories || []).slice(0, 3).join(', ') || '—') + '</div>' + ds.map(renderDetailItem).join('') + (rd.feedback ? '<div style="margin-top:10px;font-size:.74rem;color:var(--text-muted);border-top:1px solid var(--border-primary);padding-top:10px">' + escHtml(rd.feedback) + '</div>' : '') + '</div>';

          roundCard.innerHTML = headerHtml + bodyHtml;

          var header = roundCard.querySelector('.round-header');
          header.addEventListener('click', function () { toggleRound(header); });

          ct.appendChild(roundCard);
        });
      })
      .catch(function (e) { ct.innerHTML = '加载失败: ' + e.message; });
  },

  deleteSession: function (sid) {
    if (!confirm('确认删除此会话？')) return;
    fetch('/api/sessions/' + sid, { method: 'DELETE' })
      .then(function (r) {
        if (r.ok) { toast('已删除', 'success'); Sessions.load(); }
        else toast('删除失败', 'error');
      });
  }
};
