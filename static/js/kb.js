/**
 * PrimeIceAGI — 知识库管理模块
 * KB1-KB5 CRUD 操作 + 模态框
 */
'use strict';

var KB = {
  currentId: 'kb1',
  modalCb: null,
  NAMES: {
    kb1: 'TC260-003 安全标准',
    kb2: '绕过概念库',
    kb3: '绕过方法库',
    kb4: '高命中率注入模板',
    kb5: '推测的系统提示词边界'
  },

  init: function () {
    document.querySelectorAll('.kb-subtab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        document.querySelectorAll('.kb-subtab').forEach(function (b) { b.classList.remove('active'); });
        btn.classList.add('active');
        KB.switchKb(btn.dataset.kb);
      });
    });
    KB.switchKb('kb1');
  },

  switchKb: function (id) {
    KB.currentId = id;
    document.getElementById('kb-add-btn').style.display = id === 'kb5' ? 'none' : 'inline-flex';
    document.getElementById('kb-meta').textContent = KB.NAMES[id] || id;
    KB.loadData();
  },

  loadData: function () {
    var ct = document.getElementById('kb-entries');
    fetch('/api/kb/' + KB.currentId + '/data')
      .then(function (r) { return r.json(); })
      .then(function (resp) { KB.renderEntries(resp.data || resp); })
      .catch(function (e) { ct.innerHTML = '加载失败: ' + e.message; });
  },

  renderEntries: function (data) {
    var ct = document.getElementById('kb-entries');
    var es = [];

    if (KB.currentId === 'kb1') {
      var cats = data.categories || {};
      for (var k in cats) {
        if (!cats.hasOwnProperty(k)) continue;
        var v = cats[k];
        var ss = v.subcategories || {};
        es.push({ key: k, name: v.name || k, desc: '优先级' + v.priority + ' | ' + Object.keys(ss).length + '小类 | 难度' + v.difficulty });
      }
    } else if (KB.currentId === 'kb5') {
      var infs = data.inferences || [];
      for (var i = 0; i < infs.length; i++) {
        var inf = infs[i];
        es.push({ key: inf.inference_id || '', name: '推测 #' + (inf.round || '?') + ' (置信度:' + (inf.confidence || '?') + ')', desc: inf.model_identity || '' });
      }
    } else {
      var m = KB.currentId === 'kb2' ? 'concepts' : (KB.currentId === 'kb3' ? 'methods' : 'templates');
      var items = data[m] || {};
      for (var k in items) {
        if (!items.hasOwnProperty(k)) continue;
        var v = items[k];
        es.push({ key: k, name: v.name || k, desc: (v.description || v.category || v.template_text || '').substring(0, 80) });
      }
    }

    if (es.length === 0) {
      ct.innerHTML = '<div style="color:var(--text-muted);font-size:.82rem">暂无条目</div>';
      return;
    }

    ct.innerHTML = '';
    es.forEach(function (e) {
      var entry = document.createElement('div');
      entry.className = 'kb-entry';

      var info = document.createElement('div');
      info.className = 'kb-entry-info';
      info.innerHTML = '<div class="kb-entry-name">' + escHtml(e.name) + ' <span style="color:var(--text-muted);font-size:.68rem">[' + escHtml(e.key) + ']</span></div><div class="kb-entry-desc">' + escHtml(e.desc) + '</div>';

      var actions = document.createElement('div');
      actions.className = 'kb-entry-actions';

      if (KB.currentId !== 'kb5') {
        var editBtn = document.createElement('button');
        editBtn.className = 'btn btn-ghost btn-xs';
        editBtn.textContent = '编辑';
        editBtn.addEventListener('click', (function (key) {
          return function () { KB.editEntry(key); };
        })(e.key));
        actions.appendChild(editBtn);
      }

      var delBtn = document.createElement('button');
      delBtn.className = 'btn btn-ghost btn-xs';
      delBtn.style.color = 'var(--danger-coral)';
      delBtn.textContent = '删除';
      delBtn.addEventListener('click', (function (key) {
        return function () { KB.deleteEntry(key); };
      })(e.key));
      actions.appendChild(delBtn);

      entry.appendChild(info);
      entry.appendChild(actions);
      ct.appendChild(entry);
    });
  },

  addEntry: function () {
    KB.openModal('新建条目', {}, function (f) {
      return fetch('/api/kb/' + KB.currentId + '/entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(f)
      }).then(function (r) {
        if (!r.ok) return r.json().then(function (e) { toast(e.error || '保存失败', 'error'); return false; });
        return true;
      });
    });
  },

  editEntry: function (key) {
    fetch('/api/kb/' + KB.currentId + '/data')
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        var d = resp.data || resp;
        var m = KB.currentId === 'kb2' ? 'concepts' : (KB.currentId === 'kb3' ? 'methods' : (KB.currentId === 'kb4' ? 'templates' : 'categories'));
        var ex = (d[m] || {})[key] || {};
        KB.openModal('编辑条目: ' + key, ex, function (f) {
          return fetch('/api/kb/' + KB.currentId + '/entries/' + key, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(f)
          }).then(function (r) {
            if (!r.ok) return r.json().then(function (e) { toast(e.error || '保存失败', 'error'); return false; });
            return true;
          });
        }, key);
      })
      .catch(function () {});
  },

  deleteEntry: function (key) {
    if (!confirm('确认删除 "' + key + '"？')) return;
    var ep = KB.currentId === 'kb5' ? '/api/kb/kb5/inferences/' + key : '/api/kb/' + KB.currentId + '/entries/' + key;
    fetch(ep, { method: 'DELETE' })
      .then(function (r) {
        if (r.ok) { toast('已删除', 'success'); KB.loadData(); }
        else r.json().then(function (e) { toast(e.error || '删除失败', 'error'); });
      });
  },
  openModal: function (title, data, cb, editKey) {
    document.getElementById('kb-modal-title').textContent = title;
    KB.modalCb = cb;
    var h = '';

    if (KB.currentId === 'kb1') {
      h += '<div class="form-group"><label>类簇编号 (key)</label><input id="mf-key" value="' + escHtml(data.key || editKey || '') + '" placeholder="如 G" ' + (editKey ? 'readonly' : '') + '></div>';
      h += '<div class="form-group"><label>名称</label><input id="mf-name" value="' + escHtml(data.name || '') + '" placeholder="如 政治敏感内容"></div>';
      h += '<div class="form-group"><label>优先级</label><select id="mf-priority"><option value="P0"' + (data.priority === 'P0' ? ' selected' : '') + '>P0</option><option value="P1"' + (data.priority === 'P1' ? ' selected' : '') + '>P1</option><option value="P2"' + (data.priority === 'P2' ? ' selected' : '') + '>P2</option></select></div>';
      h += '<div class="form-group"><label>权重 (0-1)</label><input id="mf-weight" value="' + escHtml(data.weight || '0.1') + '" placeholder="0.1"></div>';
      h += '<div class="form-group"><label>描述</label><input id="mf-description" value="' + escHtml(data.description || '') + '"></div>';
      h += '<div class="form-group"><label>防御特征</label><input id="mf-defense_profile" value="' + escHtml(data.defense_profile || '') + '"></div>';
      h += '<div class="form-group"><label>难度 (1-5)</label><input id="mf-difficulty" type="number" min="1" max="5" value="' + escHtml(data.difficulty || '1') + '"></div>';
      h += '<div class="form-group"><label>子类 (JSON)</label><textarea id="mf-subcategories" style="min-height:80px">' + escHtml(JSON.stringify(data.subcategories || {}, null, 2)) + '</textarea></div>';
    } else if (KB.currentId === 'kb2') {
      h += '<div class="form-group"><label>概念 key</label><input id="mf-key" value="' + escHtml(editKey || '') + '" placeholder="my_concept" ' + (editKey ? 'readonly' : '') + '></div>';
      h += '<div class="form-group"><label>名称</label><input id="mf-name" value="' + escHtml(data.name || '') + '" placeholder="概念名称"></div>';
      h += '<div class="form-group"><label>层级</label><input id="mf-layer" value="' + escHtml(data.layer || '') + '" placeholder="语义层/编码层/认知层/结构层/元层"></div>';
      h += '<div class="form-group"><label>原理</label><textarea id="mf-principle" style="min-height:60px">' + escHtml(data.principle || '') + '</textarea></div>';
      h += '<div class="form-group"><label>成功率预估</label><input id="mf-success_rate_hint" value="' + escHtml(data.success_rate_hint || '') + '" placeholder="如 中高 (60-75%)"></div>';
      h += '<div class="form-group"><label>提示词模板</label><textarea id="mf-prompt_template" style="min-height:60px">' + escHtml(data.prompt_template || '') + '</textarea></div>';
    } else if (KB.currentId === 'kb3') {
      h += '<div class="form-group"><label>方法 key</label><input id="mf-key" value="' + escHtml(editKey || '') + '" placeholder="my_method" ' + (editKey ? 'readonly' : '') + '></div>';
      h += '<div class="form-group"><label>名称</label><input id="mf-name" value="' + escHtml(data.name || '') + '" placeholder="方法名称"></div>';
      h += '<div class="form-group"><label>分类</label><input id="mf-category" value="' + escHtml(data.category || '') + '" placeholder="如 身份伪装"></div>';
      h += '<div class="form-group"><label>描述</label><input id="mf-description" value="' + escHtml(data.description || '') + '"></div>';
      h += '<div class="form-group"><label>模板</label><textarea id="mf-template" style="min-height:60px">' + escHtml(data.template || '') + '</textarea></div>';
    } else if (KB.currentId === 'kb4') {
      h += '<div class="form-group"><label>条目 ID</label><input id="mf-key" value="' + escHtml(editKey || '') + '" placeholder="tpl_001" ' + (editKey ? 'readonly' : '') + '></div>';
      h += '<div class="form-group"><label>名称</label><input id="mf-name" value="' + escHtml(data.name || '') + '" placeholder="模板名称"></div>';
      h += '<div class="form-group"><label>分类</label><input id="mf-category" value="' + escHtml(data.category || '') + '" placeholder="如 系统指令注入"></div>';
      h += '<div class="form-group"><label>模板内容</label><textarea id="mf-template_text" style="min-height:100px">' + escHtml(data.template_text || '') + '</textarea></div>';
      h += '<div class="form-group"><label>成功率预估</label><input id="mf-hit_rate_hint" value="' + escHtml(data.hit_rate_hint || '') + '" placeholder="如 75%"></div>';
      h += '<div class="form-group"><label>标签 (逗号分隔)</label><input id="mf-tags" value="' + escHtml((data.tags || []).join(', ')) + '"></div>';
    }

    document.getElementById('kb-modal-fields').innerHTML = h;
    document.getElementById('kb-modal').classList.add('active');

    document.getElementById('kb-modal-save').onclick = function () {
      var f = KB.collectFields();
      if (!f) { toast('请填写必填字段', 'error'); return; }
      var result = cb(f);
      if (result && result.then) {
        result.then(function (ok) {
          if (ok) { KB.closeModal(); KB.loadData(); }
        });
      } else if (result) {
        KB.closeModal(); KB.loadData();
      }
    };
  },
  collectFields: function () {
    var f = {};
    var ke = document.getElementById('mf-key');
    if (ke) { f.key = ke.value.trim(); if (!f.key) return null; }
    var gv = function (id) { var e = document.getElementById(id); return e ? e.value.trim() : ''; };

    if (KB.currentId === 'kb1') {
      f.name = gv('mf-name') || '未命名';
      f.priority = gv('mf-priority') || 'P2';
      f.weight = parseFloat(gv('mf-weight')) || 0.1;
      f.description = gv('mf-description');
      f.defense_profile = gv('mf-defense_profile');
      f.difficulty = parseInt(gv('mf-difficulty')) || 1;
      try { f.subcategories = JSON.parse(gv('mf-subcategories') || '{}'); } catch (e) { f.subcategories = {}; }
    } else if (KB.currentId === 'kb2') {
      f.name = gv('mf-name') || '未命名';
      f.layer = gv('mf-layer');
      f.principle = gv('mf-principle');
      f.success_rate_hint = gv('mf-success_rate_hint');
      f.prompt_template = gv('mf-prompt_template');
      f.applicable_models = [];
      f.description = '';
    } else if (KB.currentId === 'kb3') {
      f.name = gv('mf-name') || '未命名';
      f.category = gv('mf-category');
      f.description = gv('mf-description');
      f.template = gv('mf-template');
    } else if (KB.currentId === 'kb4') {
      f.entry_id = gv('mf-key');
      f.name = gv('mf-name') || '未命名';
      f.category = gv('mf-category');
      f.template_text = gv('mf-template_text');
      f.hit_rate_hint = gv('mf-hit_rate_hint');
      f.tags = gv('mf-tags').split(',').map(function (s) { return s.trim(); }).filter(Boolean);
    }
    return f;
  },

  closeModal: function () {
    document.getElementById('kb-modal').classList.remove('active');
    KB.modalCb = null;
  }
};

// 初始化 KB subtab 事件
document.addEventListener('DOMContentLoaded', function () {
  KB.init();

  // 模态框取消按钮
  document.getElementById('kb-modal-cancel').addEventListener('click', function () {
    KB.closeModal();
  });
});
