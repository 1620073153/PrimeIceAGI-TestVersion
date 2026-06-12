/**
 * PrimeIceAGI — DAG 可视化模块
 * 管理测试流水线节点状态、计时器、卡住检测
 */
'use strict';

var DAG = {
  NODES: ['agent1', 'parallel', 'signal', 'judge', 'deepener', 'arbitrator'],
  STUCK_MS: 30000,
  timers: {},
  stuckCheck: null,
  liveTimer: null,

  setAll: function (state) {
    DAG.NODES.forEach(function (n) {
      var el = document.querySelector('.dag-node[data-node="' + n + '"]');
      if (el) {
        el.className = 'dag-node ' + state;
        el.querySelector('.node-time').textContent = '--';
      }
    });
    DAG.timers = {};
  },

  setNode: function (n, state) {
    var el = document.querySelector('.dag-node[data-node="' + n + '"]');
    if (!el) return;
    el.className = 'dag-node ' + state;
    var tm = el.querySelector('.node-time');

    if (state === 'active') {
      DAG.timers[n] = Date.now();
      tm.textContent = '0s';
      tm.style.color = 'var(--accent-cyan)';
    } else if (state === 'done') {
      var start = DAG.timers[n];
      tm.textContent = start ? ((Date.now() - start) / 1000).toFixed(0) + 's' : 'ok';
      tm.style.color = 'var(--success-emerald)';
      delete DAG.timers[n];
    } else if (state === 'error') {
      tm.textContent = 'err';
      tm.style.color = 'var(--danger-coral)';
      delete DAG.timers[n];
    } else {
      tm.textContent = '--';
      tm.style.color = 'var(--text-muted)';
      delete DAG.timers[n];
    }
  },

  stuckDetect: function () {
    var now = Date.now();
    for (var n in DAG.timers) {
      if (!DAG.timers.hasOwnProperty(n)) continue;
      var el = document.querySelector('.dag-node[data-node="' + n + '"]');
      if (!el) continue;
      var elapsed = (now - DAG.timers[n]) / 1000;
      el.querySelector('.node-time').textContent = elapsed.toFixed(0) + 's';
      if (now - DAG.timers[n] > DAG.STUCK_MS && el.classList.contains('active')) {
        el.classList.add('stuck');
      }
    }
  },

  startMonitor: function () {
    DAG.stopMonitor();
    DAG.stuckCheck = setInterval(DAG.stuckDetect, 5000);
    DAG.liveTimer = setInterval(function () {
      var now = Date.now();
      for (var n in DAG.timers) {
        if (!DAG.timers.hasOwnProperty(n)) continue;
        var el = document.querySelector('.dag-node[data-node="' + n + '"]');
        if (el && el.classList.contains('active')) {
          el.querySelector('.node-time').textContent = ((now - DAG.timers[n]) / 1000).toFixed(0) + 's';
          el.querySelector('.node-time').style.color = 'var(--accent-cyan)';
        }
      }
    }, 1000);
  },

  stopMonitor: function () {
    if (DAG.stuckCheck) { clearInterval(DAG.stuckCheck); DAG.stuckCheck = null; }
    if (DAG.liveTimer) { clearInterval(DAG.liveTimer); DAG.liveTimer = null; }
  }
};
