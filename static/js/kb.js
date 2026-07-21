/**
 * PrimeIceAGI — 知识库管理模块
 * KB1-KB5 CRUD 操作 + 模态框
 */
'use strict';

var KB = {
  currentId: 'kb1',
  modalCb: null,
  kb5State: null,
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
    KB.toggleKb5Controls(id === 'kb5');
    if (id === 'kb5') {
      KB.refreshKb5State().finally(function () { KB.loadData(); });
      return;
    }
    KB.loadData();
  },

  loadData: function () {
    var ct = document.getElementById('kb-entries');
    fetch('/api/kb/' + KB.currentId + '/data')
      .then(function (r) { return r.json(); })
      .then(function (resp) { KB.renderEntries(resp.data || resp); })
      .catch(function (e) { ct.innerHTML = '加载失败: ' + e.message; });
  },

  toggleKb5Controls: function (active) {
    var btn = document.getElementById('kb5-delete-btn');
    var hint = document.getElementById('kb5-delete-hint');
    if (!btn || !hint) return;
    btn.style.display = active ? 'inline-flex' : 'none';
    hint.style.display = active ? 'block' : 'none';
    if (!active) {
      hint.textContent = '';
    }
  },

  refreshKb5State: function () {
    return fetch('/api/kb/kb5')
      .then(function (r) { return r.json(); })
      .then(function (resp) {
        var data = resp.data || {};
        KB.kb5State = data;
        var hint = document.getElementById('kb5-delete-hint');
        if (!hint) return data;
        if (data.in_use) {
          hint.textContent = 'KB5 正在被任务 ' + (data.task_id || '') + ' 使用中，请先停止任务或等待完成后再删除。';
          document.getElementById('kb5-delete-btn').disabled = true;
        } else {
          hint.textContent = data.exists ? '可直接删除 KB5，测试结束后也可在结果区清理。' : 'KB5 当前不存在，可等待系统自动重建。';
          document.getElementById('kb5-delete-btn').disabled = false;
        }
        return data;
      })
      .catch(function () { return null; });
  },

  openKb5DeleteModal: function () {
    document.getElementById('kb5-delete-modal').classList.add('active');
  },

  closeKb5DeleteModal: function () {
    document.getElementById('kb5-delete-modal').classList.remove('active');
  },

  deleteKb5: function () {
    return fetch('/api/kb/kb5', { method: 'DELETE' })
      .then(function (r) { return r.json().then(function (data) { return { status: r.status, data: data }; }); })
      .then(function (res) {
        if (!res.data.ok) {
          var msg = (res.data.error && res.data.error.message) || res.data.error || '删除失败';
          toast(msg, 'error');
          return false;
        }
        toast('KB5 已删除', 'success');
        KB.closeKb5DeleteModal();
        KB.refreshKb5State();
        KB.loadData();
        return true;
      })
      .catch(function () { toast('删除 KB5 失败', 'error'); return false; });
  },

  showKb5CleanupPrompt: function () {
    var banner = document.getElementById('kb5-cleanup-banner');
    var section = document.getElementById('kb5-cleanup-actions');
    if (banner) banner.style.display = 'flex';
    if (section) {
      section.style.display = 'block';
      document.getElementById('kb5-cleanup-hint').textContent = '本次测试已完成，可点击按钮清理 KB5。';
    }
  },

  hideKb5CleanupPrompt: function () {
    var banner = document.getElementById('kb5-cleanup-banner');
    if (banner) banner.style.display = 'none';
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
        es.push({ key: inf.inference_id || ('r' + inf.round), name: '第' + (inf.round || '?') + '轮边界推测', desc: (inf.summary || inf.model_identity || '').substring(0, 120) });
      }
      // Fix #7: 渲染 session_profiles（最多5条）
      var profiles = data.session_profiles || [];
      for (var pi = 0; pi < Math.min(profiles.length, 5); pi++) {
        var prof = profiles[pi];
        var profKey = 'profile-' + (prof.session_id || pi);
        es.push({ key: profKey, name: '画像: ' + (prof.session_id || '?'), desc: (prof.kb5_summary || '').substring(0, 120) });
      }
      // Fix #7: 渲染 boundary_records 汇总统计行
      var records = data.boundary_records || [];
      if (records.length > 0) {
        var bypCount = 0, blkCount = 0;
        for (var ri = 0; ri < records.length; ri++) {
          if (records[ri].outcome === 'bypassed') bypCount++;
          else blkCount++;
        }
        es.push({ key: 'boundary-summary', name: '边界记录汇总', desc: '绕过' + bypCount + '/阻断' + blkCount + '/共' + records.length + '条' });
      }
    } else if (KB.currentId === 'kb4') {
      var tpls = data.templates || {};
      for (var k in tpls) {
        if (!tpls.hasOwnProperty(k)) continue;
        var v = tpls[k];
        var preview = (v.template_text || '').substring(0, 50);
        es.push({ key: k, name: k, desc: preview });
      }
    } else {
      var m = KB.currentId === 'kb2' ? 'concepts' : 'methods';
      var items = data[m] || {};
      for (var k in items) {
        if (!items.hasOwnProperty(k)) continue;
        var v = items[k];
        es.push({ key: k, name: k, desc: (v.description || v.category || '').substring(0, 80) });
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
      delBtn.style.color = 'var(--danger)';
      delBtn.textContent = '删除';
      delBtn.addEventListener('click', (function (key) {
        return function () { KB.deleteEntry(key); };
      })(e.key));
      if (KB.currentId === 'kb5' && KB.kb5State && KB.kb5State.in_use) {
        delBtn.disabled = true;
        delBtn.title = 'KB5 正在被测试任务使用，请先停止任务或等待完成后再删除';
      }
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
        else r.json().then(function (e) { toast((e.error && e.error.message) || e.error || '删除失败', 'error'); });
      });
  },

  deleteKb5EntryPoint: function () {
    var state = KB.kb5State || {};
    if (state.in_use) {
      toast('KB5 正在被测试任务使用，请先停止任务或等待完成后再删除', 'error');
      return;
    }
    KB.openKb5DeleteModal();
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
      h += '<div class="form-group"><label>概念名称 (key)</label><input id="mf-key" value="' + escHtml(editKey || '') + '" placeholder="如 认知层次陷阱" ' + (editKey ? 'readonly' : '') + '></div>';
      h += '<div class="form-group"><label>层级</label><input id="mf-layer" value="' + escHtml(data.layer || '') + '" placeholder="语义层/编码层/认知层/结构层/元层"></div>';
      h += '<div class="form-group"><label>原理</label><textarea id="mf-principle" style="min-height:60px">' + escHtml(data.principle || '') + '</textarea></div>';
      h += '<div class="form-group"><label>成功率预估</label><input id="mf-success_rate_hint" value="' + escHtml(data.success_rate_hint || '') + '" placeholder="如 中高 (60-75%)"></div>';
      h += '<div class="form-group"><label>提示词模板</label><textarea id="mf-prompt_template" style="min-height:60px">' + escHtml(data.prompt_template || '') + '</textarea></div>';
    } else if (KB.currentId === 'kb3') {
      h += '<div class="form-group"><label>方法名称 (key)</label><input id="mf-key" value="' + escHtml(editKey || '') + '" placeholder="如 角色扮演" ' + (editKey ? 'readonly' : '') + '></div>';
      h += '<div class="form-group"><label>分类</label><input id="mf-category" value="' + escHtml(data.category || '') + '" placeholder="如 身份伪装"></div>';
      h += '<div class="form-group"><label>描述</label><input id="mf-description" value="' + escHtml(data.description || '') + '"></div>';
      h += '<div class="form-group"><label>模板</label><textarea id="mf-template" style="min-height:60px">' + escHtml(data.template || '') + '</textarea></div>';
    } else if (KB.currentId === 'kb4') {
      h += '<div class="form-group"><label>条目 ID</label><input id="mf-key" value="' + escHtml(editKey || '') + '" placeholder="自动生成 (t01, t02...)" ' + (editKey ? 'readonly' : '') + '><span class="hint">留空则自动递增</span></div>';
      var curCat = data.category || '';
      h += '<div class="form-group"><label>目标子类</label><select id="mf-category"><option value="">不指定</option>';
      h += '<optgroup label="A1 违反社会主义核心价值观">';
      h += '<option value="A1-a"' + (curCat==='A1-a'?' selected':'') + '>A1-a 煽动颠覆国家政权</option>';
      h += '<option value="A1-b"' + (curCat==='A1-b'?' selected':'') + '>A1-b 危害国家安全和利益</option>';
      h += '<option value="A1-c"' + (curCat==='A1-c'?' selected':'') + '>A1-c 煽动分裂国家</option>';
      h += '<option value="A1-d"' + (curCat==='A1-d'?' selected':'') + '>A1-d 宣扬恐怖主义</option>';
      h += '<option value="A1-e"' + (curCat==='A1-e'?' selected':'') + '>A1-e 宣扬民族仇恨</option>';
      h += '<option value="A1-f"' + (curCat==='A1-f'?' selected':'') + '>A1-f 宣扬暴力、淫秽色情</option>';
      h += '<option value="A1-g"' + (curCat==='A1-g'?' selected':'') + '>A1-g 传播虚假有害信息</option>';
      h += '<option value="A1-h"' + (curCat==='A1-h'?' selected':'') + '>A1-h 其他法律禁止内容</option>';
      h += '</optgroup><optgroup label="A2 歧视性内容">';
      h += '<option value="A2-a"' + (curCat==='A2-a'?' selected':'') + '>A2-a 民族歧视</option>';
      h += '<option value="A2-b"' + (curCat==='A2-b'?' selected':'') + '>A2-b 信仰歧视</option>';
      h += '<option value="A2-c"' + (curCat==='A2-c'?' selected':'') + '>A2-c 国别歧视</option>';
      h += '<option value="A2-d"' + (curCat==='A2-d'?' selected':'') + '>A2-d 地域歧视</option>';
      h += '<option value="A2-e"' + (curCat==='A2-e'?' selected':'') + '>A2-e 性别歧视</option>';
      h += '<option value="A2-f"' + (curCat==='A2-f'?' selected':'') + '>A2-f 年龄歧视</option>';
      h += '<option value="A2-g"' + (curCat==='A2-g'?' selected':'') + '>A2-g 职业歧视</option>';
      h += '<option value="A2-h"' + (curCat==='A2-h'?' selected':'') + '>A2-h 健康歧视</option>';
      h += '<option value="A2-i"' + (curCat==='A2-i'?' selected':'') + '>A2-i 其他歧视</option>';
      h += '</optgroup><optgroup label="A3 商业违法违规">';
      h += '<option value="A3-a"' + (curCat==='A3-a'?' selected':'') + '>A3-a 侵犯知识产权</option>';
      h += '<option value="A3-b"' + (curCat==='A3-b'?' selected':'') + '>A3-b 违反商业道德</option>';
      h += '<option value="A3-c"' + (curCat==='A3-c'?' selected':'') + '>A3-c 泄露商业秘密</option>';
      h += '<option value="A3-d"' + (curCat==='A3-d'?' selected':'') + '>A3-d 垄断和不正当竞争</option>';
      h += '<option value="A3-e"' + (curCat==='A3-e'?' selected':'') + '>A3-e 其他商业违规</option>';
      h += '</optgroup><optgroup label="A4 侵犯他人合法权益">';
      h += '<option value="A4-a"' + (curCat==='A4-a'?' selected':'') + '>A4-a 危害身心健康</option>';
      h += '<option value="A4-b"' + (curCat==='A4-b'?' selected':'') + '>A4-b 侵害肖像权</option>';
      h += '<option value="A4-c"' + (curCat==='A4-c'?' selected':'') + '>A4-c 侵害名誉权</option>';
      h += '<option value="A4-d"' + (curCat==='A4-d'?' selected':'') + '>A4-d 侵害荣誉权</option>';
      h += '<option value="A4-e"' + (curCat==='A4-e'?' selected':'') + '>A4-e 侵害隐私权</option>';
      h += '<option value="A4-f"' + (curCat==='A4-f'?' selected':'') + '>A4-f 侵害个人信息权益</option>';
      h += '<option value="A4-g"' + (curCat==='A4-g'?' selected':'') + '>A4-g 侵犯其他合法权益</option>';
      h += '</optgroup><optgroup label="A5 无法满足特定服务安全需求">';
      h += '<option value="A5-a"' + (curCat==='A5-a'?' selected':'') + '>A5-a 内容不准确</option>';
      h += '<option value="A5-b"' + (curCat==='A5-b'?' selected':'') + '>A5-b 内容不可靠</option>';
      h += '</optgroup></select><span class="hint">指定后该模板将计入对应子类的覆盖率</span></div>';
      h += '<div class="form-group"><label>模板内容</label><textarea id="mf-template_text" style="min-height:200px">' + escHtml(data.template_text || '') + '</textarea></div>';
      h += '<div class="form-group"><label>批量添加</label><textarea id="mf-batch" style="min-height:80px" placeholder="多条模板用 ===== 分隔，批量添加时忽略上方内容"></textarea><span class="hint">可选：粘贴多条模板，用 ===== 分隔</span></div>';
    }

    document.getElementById('kb-modal-fields').innerHTML = h;
    document.getElementById('kb-modal').classList.add('active');

    document.getElementById('kb-modal-save').onclick = function () {
      var f = KB.collectFields();
      if (!f) { toast('请填写必填字段', 'error'); return; }

      // KB4 批量添加模式
      if (KB.currentId === 'kb4' && f.batch_text) {
        var items = f.batch_text.split('=====').map(function (s) { return s.trim(); }).filter(Boolean);
        if (items.length === 0) { toast('批量内容为空', 'error'); return; }
        var promises = items.map(function (text) {
          return fetch('/api/kb/kb4/entries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ template_text: text })
          });
        });
        Promise.all(promises).then(function (results) {
          var ok = results.filter(function (r) { return r.ok; }).length;
          toast('批量添加 ' + ok + '/' + items.length + ' 条', ok === items.length ? 'success' : 'error');
          KB.closeModal(); KB.loadData();
        });
        return;
      }

      // KB4 单条：如果没有 template_text 也没有 batch_text 则报错
      if (KB.currentId === 'kb4' && !f.template_text && !f.batch_text) {
        toast('请填写模板内容', 'error'); return;
      }

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
    if (ke) {
      f.key = ke.value.trim();
      // KB4 允许 key 为空（服务端自动生成）
      if (!f.key && KB.currentId !== 'kb4') return null;
    }
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
      f.layer = gv('mf-layer');
      f.principle = gv('mf-principle');
      f.success_rate_hint = gv('mf-success_rate_hint');
      f.prompt_template = gv('mf-prompt_template');
      f.applicable_models = [];
      f.description = '';
    } else if (KB.currentId === 'kb3') {
      f.category = gv('mf-category');
      f.description = gv('mf-description');
      f.template = gv('mf-template');
    } else if (KB.currentId === 'kb4') {
      f.entry_id = gv('mf-key');
      f.category = gv('mf-category');
      f.template_text = gv('mf-template_text');
      f.batch_text = gv('mf-batch');
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
  document.getElementById('kb5-delete-btn').addEventListener('click', function () {
    KB.deleteKb5EntryPoint();
  });
  document.getElementById('kb5-delete-cancel').addEventListener('click', function () {
    KB.closeKb5DeleteModal();
  });
  document.getElementById('kb5-delete-confirm').addEventListener('click', function () {
    KB.deleteKb5();
  });
  document.getElementById('kb5-banner-action').addEventListener('click', function () {
    KB.deleteKb5EntryPoint();
  });
  document.getElementById('kb5-cleanup-btn').addEventListener('click', function () {
    KB.deleteKb5EntryPoint();
  });
});
