/* LitMemory SPA — vanilla JS, no build step. */
(() => {
  "use strict";

  const NOTE_LABELS = { paper: "论文", note: "笔记", log: "记录" };
  const MEMORY_LABELS = {
    preference: "研究偏好",
    decision: "已定结论",
    working_note: "进行中",
    fact: "重要事实",
    constraint: "约束条件",
  };
  const ROUTES = {
    dashboard: { title: "工作台", crumb: "工作台" },
    library: { title: "文献库", crumb: "文献库" },
    search: { title: "语义检索", crumb: "语义检索" },
    memory: { title: "研究记忆", crumb: "研究记忆" },
    report: { title: "组会周报", crumb: "组会周报" },
  };

  const state = {
    route: "dashboard",
    notes: [],
    kinds: { ...NOTE_LABELS },
    memoryKinds: { ...MEMORY_LABELS },
    scope: "",
    health: null,
    libraryFilter: "all",
    libraryQuery: "",
    searchResult: null,
    searchParams: { query: "", kind: "all", yearFrom: "", yearTo: "", tags: "", topK: 8 },
    recall: null,
    report: null,
    busy: false,
  };

  const view = () => document.getElementById("view");
  const modal = () => document.getElementById("modal");
  const modalCard = () => document.getElementById("modal-card");

  /* ------------------------------------------------------------------ utils */
  const esc = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const fmt = (ts) => {
    if (!ts) return "—";
    const raw = String(ts).replace("T", " ");
    return raw.slice(0, raw.length > 10 ? 16 : 10);
  };

  const pct = (n) => {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
    return Number(n).toFixed(3);
  };

  const tagsOf = (note) => {
    if (Array.isArray(note?.tags)) return note.tags.filter(Boolean);
    return String(note?.tags || "")
      .split(/[,，;；]/)
      .map((t) => t.trim())
      .filter(Boolean);
  };

  function toast(message, bad = false) {
    const stack = document.getElementById("toasts");
    const node = document.createElement("div");
    node.className = "toast" + (bad ? " bad" : "");
    node.textContent = message;
    stack.appendChild(node);
    setTimeout(() => {
      node.style.opacity = "0";
      node.style.transition = "opacity .25s";
      setTimeout(() => node.remove(), 260);
    }, 3400);
  }

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    let payload = null;
    try {
      payload = await response.json();
    } catch (err) {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload?.detail;
      throw new Error(typeof detail === "string" ? detail : `请求失败（HTTP ${response.status}）`);
    }
    return payload;
  }

  function openModal(html) {
    modalCard().innerHTML = html;
    modal().hidden = false;
    document.body.style.overflow = "hidden";
    modalCard().querySelectorAll("[data-close]").forEach((btn) =>
      btn.addEventListener("click", closeModal)
    );
    const first = modalCard().querySelector("input, textarea, select");
    if (first) setTimeout(() => first.focus(), 40);
  }

  function closeModal() {
    modal().hidden = true;
    modalCard().innerHTML = "";
    document.body.style.overflow = "";
  }

  function highlight(text, query) {
    const safe = esc(text);
    const raw = String(query || "")
      .split(/[\s,，。；;:：!！?？、/\\|()（）【】]+/)
      .map((t) => t.trim())
      .filter((t) => t.length >= 2)
      .slice(0, 6);
    const terms = [];
    raw.forEach((term) => {
      if (term.length <= 8) {
        terms.push(term);
      } else {
        terms.push(term.slice(0, 6), term.slice(-6));
      }
    });
    if (!terms.length) return safe;
    const pattern = new RegExp(
      "(" + terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")",
      "gi"
    );
    return safe.replace(pattern, "<mark>$1</mark>");
  }

  function badgeFor(kind) {
    const cls = ["paper", "note", "log"].includes(kind) ? kind : "note";
    return `<span class="badge ${cls}">${esc(NOTE_LABELS[kind] || kind || "条目")}</span>`;
  }

  function memoryBadge(kind, label) {
    return `<span class="badge kind-${esc(kind)}">${esc(label || MEMORY_LABELS[kind] || kind)}</span>`;
  }

  function kindCounts(notes) {
    const counts = { paper: 0, note: 0, log: 0 };
    notes.forEach((n) => {
      const key = n.kind in counts ? n.kind : "note";
      counts[key] += 1;
    });
    return counts;
  }

  /* ----------------------------------------------------------------- router */
  function currentRoute() {
    const hash = location.hash.replace(/^#\/?/, "").split("?")[0];
    return ROUTES[hash] ? hash : "dashboard";
  }

  function hashQuery() {
    const raw = location.hash;
    const idx = raw.indexOf("?");
    return new URLSearchParams(idx >= 0 ? raw.slice(idx + 1) : "");
  }

  async function navigate() {
    state.route = currentRoute();
    document.querySelectorAll("#nav a").forEach((link) => {
      link.classList.toggle("active", link.dataset.route === state.route);
    });
    const meta = ROUTES[state.route];
    document.getElementById("crumbs").innerHTML = `<b>${esc(meta.crumb)}</b> · LitMemory`;
    document.title = `${meta.title} · LitMemory`;
    document.body.classList.remove("nav-open");
    view().innerHTML = `<div class="loading">正在准备数据…</div>`;
    try {
      if (state.route === "dashboard") await renderDashboard();
      else if (state.route === "library") await renderLibrary();
      else if (state.route === "search") await renderSearch();
      else if (state.route === "memory") await renderMemory();
      else if (state.route === "report") await renderReport();
    } catch (err) {
      view().innerHTML = `<div class="empty"><strong>页面加载失败</strong>${esc(err.message)}</div>`;
      toast(err.message, true);
    }
  }

  /* -------------------------------------------------------------- dashboard */
  async function loadBootstrap() {
    try {
      const data = await api("/api/bootstrap");
      state.notes = data.notes || [];
      state.kinds = data.kinds || state.kinds;
      state.memoryKinds = data.memory_kinds || state.memoryKinds;
      state.scope = data.scope || "";
      const line = document.getElementById("scope-line");
      if (line) line.textContent = `scope · ${state.scope || "—"}`;
    } catch (err) {
      state.notes = [];
      toast(err.message, true);
    }
  }

  function renderStatus() {
    const pill = document.getElementById("status-pill");
    if (!pill) return;
    const h = state.health;
    if (!h) {
      pill.className = "status-pill";
      pill.innerHTML = "<i></i><span>连接中…</span>";
      return;
    }
    const seek = h.seekdb?.ok;
    const pc = h.powercontext?.ok;
    pill.className = "status-pill " + (seek && pc ? "ok" : "warn");
    const label = seek && pc ? "服务正常" : seek ? "记忆服务降级" : "seekdb 未连接";
    pill.innerHTML = `<i></i><span>${label}</span>`;
    pill.title = h.seekdb?.error || h.powercontext?.error || "";
  }

  async function renderDashboard() {
    await loadBootstrap();
    const [health, stats, rlogs, mlogs] = await Promise.all([
      api("/api/health").catch((err) => ({ error: err.message })),
      api("/api/stats").catch((err) => ({ error: err.message })),
      api("/api/retrieval-logs?limit=8").catch(() => ({ logs: [] })),
      api("/api/memory-logs?limit=6").catch(() => ({ logs: [] })),
    ]);
    state.health = health.error ? null : health;
    renderStatus();

    const notes = state.notes || [];
    const counts = kindCounts(notes);
    const seekdb = health.seekdb || {};
    const pc = health.powercontext || {};
    const embedding = health.embedding || {};
    const memoryOps = (mlogs.logs || []).length;

    view().innerHTML = `
      <section class="hero">
        <div class="eyebrow">Qoder × OceanBase 2026 · 科研工作流</div>
        <h1>把读过的文献，变成会积累的研究记忆。</h1>
        <p class="lead">
          LitMemory 用 <b>seekdb</b> 统一存储论文与笔记，提供向量 + 全文 + 标量过滤的混合检索；
          用 <b>PowerContext</b> 保存跨会话的研究偏好、已定结论与进行中事项。
          每次检索都有日志，每份周报都能回指证据。
        </p>
        <div class="hero-actions">
          <a class="btn primary" href="#/search">开始语义检索 →</a>
          <a class="btn" href="#/memory">查看研究记忆</a>
          <a class="btn" href="#/report">生成组会周报</a>
          <button class="btn ghost" id="seed-btn">载入/刷新示例数据</button>
        </div>
      </section>

      <div class="grid grid-3 mt-20">
        <div class="card stat">
          <span class="k">知识条目</span>
          <span class="v">${notes.length}<small>条</small></span>
          <span class="meta">论文 ${counts.paper} · 笔记 ${counts.note} · 记录 ${counts.log}</span>
        </div>
        <div class="card stat">
          <span class="k">seekdb 集合</span>
          <span class="v">${seekdb.count ?? 0}<small>向量</small></span>
          <span class="meta mono">${esc(seekdb.database || "—")} / ${esc(seekdb.collection || "—")}</span>
        </div>
        <div class="card stat">
          <span class="k">记忆操作</span>
          <span class="v">${memoryOps}<small>最近</small></span>
          <span class="meta">scope · ${esc(pc.scope || state.scope || "—")}</span>
        </div>
      </div>

      <div class="section-label"><h2>服务状态</h2><span>启动时自动检查</span></div>
      <div class="grid grid-2">
        <div class="card service">
          <div class="service-head">
            <h3>seekdb · 混合检索</h3>
            <span class="badge ${seekdb.ok ? "accent" : ""}"><span class="dot ${seekdb.ok ? "ok" : "bad"}"></span>${seekdb.ok ? "在线" : "不可用"}</span>
          </div>
          <dl>
            <dt>数据库</dt><dd class="mono">${esc(seekdb.database || "—")}</dd>
            <dt>集合</dt><dd class="mono">${esc(seekdb.collection || "—")}</dd>
            <dt>向量维度</dt><dd class="mono">${seekdb.dimension ?? "—"}</dd>
            <dt>嵌入模型</dt><dd>${esc(embedding.model || "—")} <span class="muted">(${esc(embedding.backend || "—")})</span></dd>
            ${embedding.fallback_reason ? `<dt>降级原因</dt><dd class="muted">${esc(embedding.fallback_reason)}</dd>` : ""}
            ${seekdb.error ? `<dt>错误</dt><dd style="color:var(--danger)">${esc(seekdb.error)}</dd>` : ""}
          </dl>
        </div>
        <div class="card service">
          <div class="service-head">
            <h3>PowerContext · 跨会话记忆</h3>
            <span class="badge ${pc.ok ? "accent" : ""}"><span class="dot ${pc.ok ? "ok" : "bad"}"></span>${pc.ok ? "在线" : "不可用"}</span>
          </div>
          <dl>
            <dt>scope</dt><dd class="mono">${esc(pc.scope || state.scope || "—")}</dd>
            <dt>状态</dt><dd>${pc.ok ? "可读写记忆条目" : "已降级：仅 seekdb 检索与周报可用"}</dd>
            <dt>接口</dt><dd class="mono">PowerContext Server · 127.0.0.1:8000</dd>
            ${pc.error ? `<dt>错误</dt><dd style="color:var(--danger)">${esc(pc.error)}</dd>` : ""}
          </dl>
        </div>
      </div>

      <div class="grid grid-2 mt-20 items-start">
        <div class="stack">
          <div class="card card-pad">
            <div class="flex" style="justify-content:space-between;margin-bottom:12px">
              <h3>最近检索</h3><a class="btn ghost sm" href="#/search">去检索</a>
            </div>
            ${renderRetrievalLogs(rlogs.logs || [])}
          </div>
          <div class="card card-pad">
            <h3 style="margin-bottom:10px">研究闭环</h3>
            <div class="side-list">
              <div><span>① 读文献 → 写入 seekdb</span><b>向量 + 全文</b></div>
              <div><span>② 得结论 → 写入 PowerContext</span><b>跨会话</b></div>
              <div><span>③ 开组会 → 一键生成周报</span><b>带证据</b></div>
            </div>
          </div>
        </div>
        <div class="card card-pad">
          <div class="flex" style="justify-content:space-between;margin-bottom:12px">
            <h3>最近记忆操作</h3><a class="btn ghost sm" href="#/memory">去记录</a>
          </div>
          ${renderMemoryLogs(mlogs.logs || [])}
        </div>
      </div>
    `;

    document.getElementById("seed-btn").addEventListener("click", async (event) => {
      const btn = event.currentTarget;
      btn.disabled = true;
      btn.textContent = "写入中…";
      try {
        const result = await api("/api/demo/seed", { method: "POST" });
        toast(
          `示例数据已就绪：条目 ${result.notes} 条，新增记忆 ${result.memories} 条` +
            (result.memory_error ? "（记忆服务暂不可用）" : "")
        );
        await loadBootstrap();
        await renderDashboard();
      } catch (err) {
        toast(err.message, true);
        btn.disabled = false;
        btn.textContent = "载入/刷新示例数据";
      }
    });
  }

  function renderRetrievalLogs(rows) {
    if (!rows.length) return `<div class="empty"><strong>还没有检索记录</strong>发起一次语义检索后，这里会显示引擎、耗时与命中条目。</div>`;
    return `<div class="log-list">${rows
      .map(
        (row) => `
      <div class="log-row">
        <span class="t">${esc(fmt(row.ts))}</span>
        <span class="q">${esc(row.query || "（空查询）")}<br><span class="muted mono">${esc(row.engine || "")} · ${(row.hits || []).length} 命中</span></span>
        <span class="r">${row.elapsed_ms ?? "—"} ms</span>
      </div>`
      )
      .join("")}</div>`;
  }

  function renderMemoryLogs(rows) {
    if (!rows.length) return `<div class="empty"><strong>还没有记忆操作</strong>记录一条研究偏好或让系统回忆上下文后，这里会出现审计日志。</div>`;
    return `<div class="log-list">${rows
      .map((row) => {
        const text =
          row.op === "remember"
            ? `${MEMORY_LABELS[row.kind] || row.kind || "记忆"}：${row.text || ""}`
            : row.op === "search"
            ? `检索：${row.query || ""}`
            : `准备上下文：${row.query || ""}`;
        return `
        <div class="log-row">
          <span class="t">${esc(fmt(row.ts))}</span>
          <span class="q">${esc(text)}</span>
          <span class="r">${row.elapsed_ms ?? "—"} ms</span>
        </div>`;
      })
      .join("")}</div>`;
  }

  /* ---------------------------------------------------------------- library */
  async function renderLibrary() {
    await loadBootstrap();
    const total = state.notes.length;
    const counts = kindCounts(state.notes);
    const filter = state.libraryFilter;
    const needle = state.libraryQuery.trim().toLowerCase();
    let notes = state.notes.slice();
    if (filter !== "all") notes = notes.filter((n) => n.kind === filter);
    if (needle) {
      notes = notes.filter((n) =>
        [n.title, n.content, n.authors, n.source, tagsOf(n).join(" ")]
          .join(" ")
          .toLowerCase()
          .includes(needle)
      );
    }

    view().innerHTML = `
      <div class="page-head">
        <div class="titles">
          <div class="eyebrow">seekdb · ${esc(state.health?.seekdb?.collection || "litmemory_notes")}</div>
          <h1>文献库</h1>
          <p>论文、阅读笔记与实验记录统一入库。每条内容会被本地模型向量化，同时支持全文匹配与年份、类型过滤。</p>
        </div>
        <button class="btn primary" id="add-note">＋ 新增条目</button>
      </div>

      <div class="flex wrap" style="justify-content:space-between;gap:14px">
        <div class="tabs" id="lib-tabs">
          ${["all", "paper", "note", "log"]
            .map((key) => {
              const label = key === "all" ? `全部 ${total}` : `${NOTE_LABELS[key]} ${counts[key]}`;
              return `<button class="tab ${filter === key ? "active" : ""}" data-filter="${key}">${label}</button>`;
            })
            .join("")}
        </div>
        <div class="search-bar" style="max-width:380px">
          <input type="search" id="lib-query" placeholder="按标题、作者、标签过滤…" value="${esc(state.libraryQuery)}" />
        </div>
      </div>

      <div class="section-label">
        <h2>${filter === "all" ? "全部条目" : NOTE_LABELS[filter]}</h2>
        <span>共 ${notes.length} 条</span>
      </div>

      <div class="note-list">
        ${
          notes.length
            ? notes.map(noteRow).join("")
            : `<div class="empty"><strong>没有匹配的条目</strong>调整筛选条件，或新增一条论文/笔记。</div>`
        }
      </div>
    `;

    document.getElementById("add-note").addEventListener("click", () => openNoteEditor(null));
    document.querySelectorAll("#lib-tabs .tab").forEach((tab) =>
      tab.addEventListener("click", () => {
        state.libraryFilter = tab.dataset.filter;
        renderLibrary();
      })
    );
    const input = document.getElementById("lib-query");
    input.addEventListener("input", () => {
      state.libraryQuery = input.value;
      const cursor = input.selectionStart;
      renderLibrary().then(() => {
        const next = document.getElementById("lib-query");
        if (next) {
          next.focus();
          next.setSelectionRange(cursor, cursor);
        }
      });
    });
    document.querySelectorAll("[data-note-id]").forEach((node) =>
      node.addEventListener("click", () => openNoteDetail(node.dataset.noteId))
    );
  }

  function noteRow(note) {
    const tags = tagsOf(note);
    return `
      <article class="note-item" data-note-id="${esc(note.id)}">
        <div>
          <h3>${badgeFor(note.kind)} ${esc(note.title || "未命名条目")}</h3>
          <div class="snippet">${esc(note.snippet || note.content || "").slice(0, 260)}</div>
          <div class="meta">
            ${note.authors ? `<span><b>作者</b> ${esc(note.authors)}</span>` : ""}
            ${note.year ? `<span><b>年份</b> ${esc(note.year)}</span>` : ""}
            ${note.source ? `<span><b>来源</b> ${esc(note.source)}</span>` : ""}
            <span><b>更新</b> ${esc(fmt(note.updated_at))}</span>
          </div>
        </div>
        <div class="side">
          <div class="compact-tags">${tags.slice(0, 3).map((t) => `<span class="badge plain">#${esc(t)}</span>`).join(" ")}</div>
          <span class="badge mono">${esc(note.id)}</span>
        </div>
      </article>`;
  }

  async function openNoteDetail(noteId) {
    let note;
    try {
      const data = await api(`/api/notes/${encodeURIComponent(noteId)}`);
      note = data.note;
    } catch (err) {
      toast(err.message, true);
      return;
    }
    const tags = tagsOf(note);
    openModal(`
      <div class="modal-head">
        <div class="titles">
          <div class="kv-inline">${badgeFor(note.kind)}<span class="mono">${esc(note.id)}</span></div>
          <h2 style="margin-top:8px">${esc(note.title)}</h2>
        </div>
        <button class="modal-close" data-close aria-label="关闭">×</button>
      </div>
      <div class="detail-meta">
        ${note.authors ? `<span>作者 · ${esc(note.authors)}</span>` : ""}
        ${note.year ? `<span>年份 · ${esc(note.year)}</span>` : ""}
        ${note.source ? `<span>来源 · ${esc(note.source)}</span>` : ""}
        <span>创建 · ${esc(fmt(note.created_at))}</span>
        <span>更新 · ${esc(fmt(note.updated_at))}</span>
      </div>
      <div class="flex wrap" style="gap:6px;margin-bottom:16px">
        ${tags.map((t) => `<span class="badge plain">#${esc(t)}</span>`).join("")}
      </div>
      <div class="detail-body">${esc(note.content || "（暂无正文）")}</div>
      <div class="modal-actions">
        <button class="btn danger" id="detail-delete">删除</button>
        <button class="btn" id="detail-edit">编辑</button>
        <button class="btn primary" data-close>关闭</button>
      </div>
    `);
    modalCard().querySelectorAll("[data-close]").forEach((btn) =>
      btn.addEventListener("click", closeModal)
    );
    document.getElementById("detail-edit").addEventListener("click", () => openNoteEditor(note));
    document.getElementById("detail-delete").addEventListener("click", async () => {
      if (!window.confirm(`确定删除「${note.title}」？该操作会同时从 seekdb 中移除向量。`)) return;
      try {
        await api(`/api/notes/${encodeURIComponent(note.id)}`, { method: "DELETE" });
        closeModal();
        toast("条目已删除");
        await loadBootstrap();
        renderLibrary();
      } catch (err) {
        toast(err.message, true);
      }
    });
  }

  function openNoteEditor(note) {
    const editing = Boolean(note);
    const tags = note ? tagsOf(note).join(", ") : "";
    openModal(`
      <div class="modal-head">
        <h2>${editing ? "编辑条目" : "新增条目"}</h2>
        <button class="modal-close" data-close aria-label="关闭">×</button>
      </div>
      <form id="note-form">
        <div class="field">
          <label>标题 *</label>
          <input type="text" name="title" required maxlength="500" value="${esc(note?.title || "")}" placeholder="例如：A-MEM: Agentic Memory for LLM Agents" />
        </div>
        <div class="form-row three mt-12">
          <div class="field">
            <label>类型</label>
            <select name="kind">
              ${Object.entries(NOTE_LABELS)
                .map(([key, label]) => `<option value="${key}" ${note?.kind === key ? "selected" : ""}>${label}</option>`)
                .join("")}
            </select>
          </div>
          <div class="field">
            <label>作者</label>
            <input type="text" name="authors" value="${esc(note?.authors || "")}" placeholder="Xu et al." />
          </div>
          <div class="field">
            <label>年份</label>
            <input type="number" name="year" min="1900" max="2100" value="${esc(note?.year || "")}" placeholder="2025" />
          </div>
        </div>
        <div class="form-row mt-12">
          <div class="field">
            <label>来源</label>
            <input type="text" name="source" value="${esc(note?.source || "")}" placeholder="arXiv:2502.12110 / 组会记录" />
          </div>
          <div class="field">
            <label>标签（逗号分隔）</label>
            <input type="text" name="tags" value="${esc(tags)}" placeholder="长期记忆, 混合检索" />
          </div>
        </div>
        <div class="field mt-12">
          <label>正文（摘要、笔记或实验记录）</label>
          <textarea name="content" rows="8" placeholder="写下方法要点、实验结果或你的思考…">${esc(note?.content || "")}</textarea>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn" data-close>取消</button>
          <button type="submit" class="btn primary">${editing ? "保存修改" : "写入 seekdb"}</button>
        </div>
      </form>
    `);
    modalCard().querySelectorAll("[data-close]").forEach((btn) =>
      btn.addEventListener("click", closeModal)
    );
    document.getElementById("note-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      const body = {
        title: String(form.get("title") || "").trim(),
        kind: String(form.get("kind") || "note"),
        authors: String(form.get("authors") || "").trim(),
        year: form.get("year") ? Number(form.get("year")) : null,
        source: String(form.get("source") || "").trim(),
        tags: String(form.get("tags") || "").trim(),
        content: String(form.get("content") || ""),
      };
      if (!body.title) return;
      const submit = event.target.querySelector("button[type=submit]");
      submit.disabled = true;
      submit.textContent = "写入中…";
      try {
        if (editing) {
          await api(`/api/notes/${encodeURIComponent(note.id)}`, {
            method: "PUT",
            body: JSON.stringify(body),
          });
          toast("已更新，向量同步完成");
        } else {
          await api("/api/notes", { method: "POST", body: JSON.stringify(body) });
          toast("已写入 seekdb");
        }
        closeModal();
        await loadBootstrap();
        if (state.route === "library") renderLibrary();
        else navigate();
      } catch (err) {
        toast(err.message, true);
        submit.disabled = false;
        submit.textContent = editing ? "保存修改" : "写入 seekdb";
      }
    });
  }

  /* ----------------------------------------------------------------- search */
  async function renderSearch() {
    await loadBootstrap();
    const qp = hashQuery();
    if (!state.searchParams.query && qp.get("q")) {
      state.searchParams.query = qp.get("q");
      if (qp.get("kind")) state.searchParams.kind = qp.get("kind");
    }
    const p = state.searchParams;
    const result = state.searchResult;

    view().innerHTML = `
      <div class="page-head">
        <div class="titles">
          <div class="eyebrow">seekdb hybrid retrieval</div>
          <h1>语义检索</h1>
          <p>向量近邻 + 全文匹配 + RRF 融合，先经标量过滤再排序。每条结果都带有来源条目，检索过程写入审计日志。</p>
        </div>
      </div>

      <div class="card card-pad">
        <form id="search-form">
          <div class="search-bar">
            <input type="search" name="query" id="search-query" value="${esc(p.query)}" placeholder="例如：如何在有限上下文预算内复用研究记忆？" autofocus />
            <button class="btn primary" type="submit">检索</button>
          </div>
          <div class="filters">
            <div class="field">
              <label>类型</label>
              <select name="kind">
                <option value="all" ${p.kind === "all" ? "selected" : ""}>全部</option>
                ${Object.entries(state.kinds)
                  .map(([key, label]) => `<option value="${key}" ${p.kind === key ? "selected" : ""}>${esc(label)}</option>`)
                  .join("")}
              </select>
            </div>
            <div class="field">
              <label>起始年份</label>
              <input type="number" name="yearFrom" min="1900" max="2100" value="${esc(p.yearFrom)}" placeholder="不限" />
            </div>
            <div class="field">
              <label>结束年份</label>
              <input type="number" name="yearTo" min="1900" max="2100" value="${esc(p.yearTo)}" placeholder="不限" />
            </div>
            <div class="field grow">
              <label>标签（任一命中，逗号分隔）</label>
              <input type="text" name="tags" value="${esc(p.tags)}" placeholder="长期记忆, 混合检索" />
            </div>
            <div class="field" style="flex:0 1 110px">
              <label>返回条数</label>
              <select name="topK">
                ${[5, 8, 12, 20].map((n) => `<option value="${n}" ${Number(p.topK) === n ? "selected" : ""}>${n}</option>`).join("")}
              </select>
            </div>
          </div>
        </form>
      </div>

      <div class="section-label">
        <h2>检索结果</h2>
        <span>${result ? `${esc(result.engine)} · ${result.elapsed_ms} ms · ${result.hits?.length || 0} 条` : "等待查询"}</span>
      </div>

      ${result ? renderSearchResult(result) : `<div class="empty"><strong>输入研究问题开始检索</strong>例如「记忆写入时如何建立语义链接」，或试试「混合检索 召回率」。</div>`}

      <div class="section-label"><h2>检索审计日志</h2><span>JSONL · data/logs/retrieval_logs.jsonl</span></div>
      <div class="card card-pad" id="retrieval-logs"><div class="loading" style="padding:20px 0">加载日志…</div></div>
    `;

    document.getElementById("search-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      state.searchParams = {
        query: String(form.get("query") || "").trim(),
        kind: String(form.get("kind") || "all"),
        yearFrom: String(form.get("yearFrom") || "").trim(),
        yearTo: String(form.get("yearTo") || "").trim(),
        tags: String(form.get("tags") || "").trim(),
        topK: Number(form.get("topK") || 8),
      };
      if (!state.searchParams.query) {
        toast("请输入检索问题", true);
        return;
      }
      await runSearch();
    });

    document.querySelectorAll("[data-search-again]").forEach((btn) =>
      btn.addEventListener("click", () => {
        state.searchParams.query = btn.dataset.searchAgain;
        state.searchResult = null;
        renderSearch();
      })
    );

    loadRetrievalLogs();

    if (!result && p.query) runSearch();
  }

  async function runSearch() {
    const p = state.searchParams;
    const container = document.getElementById("search-result-holder");
    if (container) container.innerHTML = `<div class="skeleton"></div>`;
    view().querySelector(".section-label span").textContent = "检索中…";
    try {
      const body = {
        query: p.query,
        top_k: p.topK,
        kinds: p.kind === "all" ? null : [p.kind],
        year_from: p.yearFrom ? Number(p.yearFrom) : null,
        year_to: p.yearTo ? Number(p.yearTo) : null,
        tags: p.tags ? p.tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean) : null,
      };
      const result = await api("/api/search", { method: "POST", body: JSON.stringify(body) });
      state.searchResult = result;
      await renderSearch();
      loadRetrievalLogs();
    } catch (err) {
      toast(err.message, true);
      const holder = document.getElementById("search-result-holder");
      if (holder) holder.innerHTML = `<div class="empty"><strong>检索失败</strong>${esc(err.message)}</div>`;
    }
  }

  function renderSearchResult(result) {
    const hits = result.hits || [];
    const embedding = result.embedding || {};
    return `
      <div id="search-result-holder">
        <div class="evidence" style="margin-bottom:16px">
          <span><b>引擎</b> ${esc(result.engine)}</span>
          <span><b>数据库</b> ${esc(result.database)}</span>
          <span><b>集合</b> ${esc(result.collection)}</span>
          <span><b>嵌入</b> ${esc(embedding.model || "—")}</span>
          <span><b>耗时</b> ${result.elapsed_ms} ms</span>
        </div>
        ${
          hits.length
            ? hits.map((hit) => searchHit(hit)).join("")
            : `<div class="empty"><strong>没有命中条目</strong>换一个更宽泛的问法，或放宽年份/标签过滤。</div>`
        }
      </div>`;
  }

  function searchHit(hit) {
    const tags = tagsOf(hit);
    return `
      <article class="result-card">
        <div class="result-head">
          <h3>${badgeFor(hit.kind)} ${highlight(hit.title || "未命名", state.searchParams.query)}</h3>
          <span class="score">${hit.score === null || hit.score === undefined ? "—" : Number(hit.score).toFixed(3)}</span>
        </div>
        <div class="result-body">${highlight(hit.snippet || "", state.searchParams.query)}</div>
        <div class="result-foot">
          ${hit.authors ? `<span>${esc(hit.authors)}</span>` : ""}
          ${hit.year ? `<span>${esc(hit.year)}</span>` : ""}
          ${hit.source ? `<span>${esc(hit.source)}</span>` : ""}
          <span class="mono">${esc(hit.id)}</span>
          ${hit.distance !== null && hit.distance !== undefined ? `<span class="mono">distance ${Number(hit.distance).toFixed(4)}</span>` : ""}
          ${tags.slice(0, 4).map((t) => `<span class="badge plain">#${esc(t)}</span>`).join("")}
          <button class="btn ghost sm" style="margin-left:auto" data-search-again="${esc(hit.title || "")}">以此为题再检索</button>
        </div>
      </article>`;
  }

  async function loadRetrievalLogs() {
    const holder = document.getElementById("retrieval-logs");
    if (!holder) return;
    try {
      const data = await api("/api/retrieval-logs?limit=12");
      holder.innerHTML = renderRetrievalLogs(data.logs || []);
    } catch (err) {
      holder.innerHTML = `<div class="muted">日志读取失败：${esc(err.message)}</div>`;
    }
  }

  /* ----------------------------------------------------------------- memory */
  async function renderMemory() {
    const [entries, mlogs] = await Promise.all([
      api("/api/memories").catch((err) => ({ entries: [], error: err.message })),
      api("/api/memory-logs?limit=6").catch(() => ({ logs: [] })),
    ]);
    state.memoryKinds = entries.kinds || state.memoryKinds;
    const rows = entries.entries || [];
    const recall = state.recall;

    view().innerHTML = `
      <div class="page-head">
        <div class="titles">
          <div class="eyebrow">PowerContext · ${esc(entries.scope || state.scope)}</div>
          <h1>研究记忆</h1>
          <p>这里保存的不是文献，而是「关于你」的研究上下文：方向偏好、已定结论、进行中事项与约束。下一次会话开始时，它们会被重新召回。</p>
        </div>
        <span class="badge accent">${rows.length} 条记忆</span>
      </div>

      ${entries.error ? `<div class="card card-pad" style="border-color:#ecd1cd;background:#fdf7f6;margin-bottom:18px"><b>PowerContext 暂不可用</b><div class="small muted" style="margin-top:4px">${esc(entries.error)}</div></div>` : ""}

      <div class="grid grid-2" style="align-items:start">
        <div>
          <div class="section-label" style="margin-top:0"><h2>记忆条目</h2><span>按类型着色</span></div>
          <div class="memory-grid" style="grid-template-columns:1fr">
            ${
              rows.length
                ? rows.map(memoryCard).join("")
                : `<div class="empty"><strong>还没有记忆条目</strong>在右侧记录一条研究偏好，或点击「载入示例数据」。</div>`
            }
          </div>
        </div>

        <div>
          <div class="section-label" style="margin-top:0"><h2>写入记忆</h2><span>长期有效</span></div>
          <form class="card card-pad" id="memory-form">
            <div class="form-row">
              <div class="field">
                <label>类型</label>
                <select name="kind">
                  ${Object.entries(state.memoryKinds)
                    .map(([key, label]) => `<option value="${key}">${esc(label)}</option>`)
                    .join("")}
                </select>
              </div>
              <div class="field">
                <label>原因（可选）</label>
                <input type="text" name="reason" placeholder="组会讨论 / 导师反馈…" />
              </div>
            </div>
            <div class="field mt-12">
              <label>内容</label>
              <textarea name="text" rows="4" required placeholder="例如：我的研究方向是 AI Agent 长期记忆，优先做混合检索对比实验。"></textarea>
            </div>
            <div class="modal-actions" style="margin-top:14px">
              <button class="btn primary" type="submit">记住这条</button>
            </div>
          </form>

          <div class="section-label"><h2>召回上下文</h2><span>search + prepare_context</span></div>
          <div class="card card-pad">
            <div class="search-bar">
              <input type="search" id="recall-query" value="${esc(recall?.query || "本周研究目标与已定结论")}" placeholder="当前任务是什么？" />
              <button class="btn" id="recall-btn">回忆</button>
            </div>
            <div class="hint" style="margin-top:8px">PowerContext 会返回最相关的记忆条目，并渲染成可直接注入提示词的上下文块。</div>
            <div style="margin-top:14px" id="recall-output">
              ${
                recall
                  ? `
                    <div class="flex wrap" style="gap:8px;margin-bottom:10px">
                      <span class="badge accent">${esc(recall.mode || "—")}</span>
                      <span class="badge">${recall.hits?.length || 0} 条命中</span>
                      <span class="badge">${esc(recall.prepared?.status || "")}</span>
                      <span class="badge mono">${recall.prepared?.content_bytes ?? 0} bytes</span>
                    </div>
                    <div class="prepared">${esc(recall.prepared?.content || "")}</div>
                    ${
                      recall.hits?.length
                        ? `<div class="side-list" style="margin-top:12px">${recall.hits
                            .map(
                              (hit) =>
                                `<div><span>${esc(hit.text)}</span><b>${Number(hit.score).toFixed(2)}</b></div>`
                            )
                            .join("")}</div>`
                        : ""
                    }
                    <div class="modal-actions" style="justify-content:flex-start;margin-top:12px">
                      <button class="btn sm" id="copy-context">复制上下文</button>
                    </div>
                  `
                  : `<div class="empty" style="padding:30px 18px"><strong>还没有召回</strong>点击「回忆」，查看 PowerContext 会如何向新会话交代你的研究背景。</div>`
              }
            </div>
          </div>
        </div>
      </div>

      <div class="section-label"><h2>记忆审计日志</h2><span>JSONL · data/logs/memory_logs.jsonl</span></div>
      <div class="card card-pad">${renderMemoryLogs(mlogs.logs || [])}</div>
    `;

    document.getElementById("memory-form").addEventListener("submit", async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      const text = String(form.get("text") || "").trim();
      if (!text) return;
      const submit = event.target.querySelector("button[type=submit]");
      submit.disabled = true;
      submit.textContent = "写入中…";
      try {
        await api("/api/memories", {
          method: "POST",
          body: JSON.stringify({
            kind: String(form.get("kind") || "fact"),
            text,
            reason: String(form.get("reason") || "").trim() || null,
          }),
        });
        toast("已写入 PowerContext");
        state.recall = null;
        renderMemory();
      } catch (err) {
        toast(err.message, true);
        submit.disabled = false;
        submit.textContent = "记住这条";
      }
    });

    document.getElementById("recall-btn").addEventListener("click", async () => {
      const query = document.getElementById("recall-query").value.trim() || "当前研究目标、偏好与进展";
      const btn = document.getElementById("recall-btn");
      btn.disabled = true;
      btn.textContent = "召回中…";
      try {
        state.recall = await api("/api/memories/recall", {
          method: "POST",
          body: JSON.stringify({ query, max_bytes: 8000 }),
        });
        await renderMemory();
      } catch (err) {
        toast(err.message, true);
        btn.disabled = false;
        btn.textContent = "回忆";
      }
    });

    const copyBtn = document.getElementById("copy-context");
    if (copyBtn) {
      copyBtn.addEventListener("click", async () => {
        const text = state.recall?.prepared?.content || "";
        try {
          await navigator.clipboard.writeText(text);
          toast("已复制到剪贴板");
        } catch (err) {
          const area = document.createElement("textarea");
          area.value = text;
          document.body.appendChild(area);
          area.select();
          document.execCommand("copy");
          area.remove();
          toast("已复制到剪贴板");
        }
      });
    }

    if (!state.recall && hashQuery().get("recall")) {
      document.getElementById("recall-btn").click();
    }
  }

  function memoryCard(entry) {
    const citation = entry.citation || {};
    const kind = entry.kind || "fact";
    const label = entry.kind_label || MEMORY_LABELS[kind] || kind;
    return `
      <article class="card memory-card">
        <div class="top">
          ${memoryBadge(kind, label)}
          <span class="badge plain mono">v${esc(entry.version ?? 1)} · ${esc((entry.state || "active") === "active" ? "生效" : "已失效")}</span>
        </div>
        <p>${esc(entry.text || "")}</p>
        <div class="id">entry_id ${esc(citation.entry_id || "—")}</div>
      </article>`;
  }

  /* ----------------------------------------------------------------- report */
  function weekRange() {
    const now = new Date();
    const offset = (now.getDay() + 6) % 7;
    const start = new Date(now);
    start.setDate(now.getDate() - offset);
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    const iso = (d) => d.toISOString().slice(0, 10);
    return { start: iso(start), end: iso(end) };
  }

  async function renderReport() {
    await loadBootstrap();
    const week = weekRange();
    const report = state.report;
    view().innerHTML = `
      <div class="page-head">
        <div class="titles">
          <div class="eyebrow">seekdb 检索 + PowerContext 记忆</div>
          <h1>组会周报</h1>
          <p>不做无根据的生成：草稿只使用本周入库的条目与当前生效的研究记忆，并在末尾附上证据索引。</p>
        </div>
      </div>

      <div class="card card-pad">
        <div class="report-toolbar">
          <div class="field">
            <label>周起始</label>
            <input type="date" id="week-start" value="${esc(report?.week_start || week.start)}" />
          </div>
          <div class="field">
            <label>周结束</label>
            <input type="date" id="week-end" value="${esc(report?.week_end || week.end)}" />
          </div>
          <button class="btn primary" id="make-report">生成周报</button>
          ${report ? `<button class="btn" id="copy-report">复制 Markdown</button><button class="btn" id="download-report">下载 .md</button>` : ""}
          <span class="spacer"></span>
          <span class="hint">草稿可编辑后直接贴进组会文档</span>
        </div>
      </div>

      <div class="section-label"><h2>${report ? "草稿预览" : "等待生成"}</h2><span>${report ? `生成于 ${esc(fmt(report.generated_at))}` : ""}</span></div>

      ${
        report
          ? `<div class="report-shell">
              <div class="card card-pad">
                <div class="markdown">${markdown(report.markdown)}</div>
                ${report.memory_error ? `<div class="hint" style="margin-top:18px;color:var(--danger)">记忆服务不可用，草稿仅基于 seekdb：${esc(report.memory_error)}</div>` : ""}
              </div>
              <div class="side-card card">
                <h3>本周数据</h3>
                <div class="side-list">
                  <div><span>候选资料</span><b>${report.stats.candidates}</b></div>
                  <div><span>论文</span><b>${report.stats.papers}</b></div>
                  <div><span>笔记 / 记录</span><b>${report.stats.notes}</b></div>
                  <div><span>记忆条目</span><b>${report.stats.memories}</b></div>
                </div>
                <h3 style="margin-top:20px">证据索引</h3>
                <div class="side-list">
                  <div><span>seekdb 条目</span><b>${report.evidence.note_ids.length}</b></div>
                  <div><span>scope</span><b style="font-size:10.5px">${esc(report.evidence.scope)}</b></div>
                </div>
                <div class="side-list" style="margin-top:10px">
                  ${(report.evidence.memory_entries || [])
                    .slice(0, 6)
                    .map(
                      (entry) =>
                        `<div><span>${esc(MEMORY_LABELS[entry.kind] || entry.kind)} · ${esc(String(entry.text || "").slice(0, 26))}…</span></div>`
                    )
                    .join("")}
                </div>
              </div>
            </div>`
          : `<div class="empty"><strong>选择周区间后点击「生成周报」</strong>系统会从 seekdb 取出该周整理的资料，并召回 PowerContext 中的研究目标与已定结论。</div>`
      }
    `;

    document.getElementById("make-report").addEventListener("click", async () => {
      const btn = document.getElementById("make-report");
      btn.disabled = true;
      btn.textContent = "生成中…";
      try {
        const start = document.getElementById("week-start").value;
        const end = document.getElementById("week-end").value;
        state.report = await api("/api/reports", {
          method: "POST",
          body: JSON.stringify({ week_start: start || null, week_end: end || null }),
        });
        await renderReport();
        toast("周报草稿已生成");
      } catch (err) {
        toast(err.message, true);
        btn.disabled = false;
        btn.textContent = "生成周报";
      }
    });

    const copyBtn = document.getElementById("copy-report");
    if (copyBtn)
      copyBtn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(report.markdown);
          toast("Markdown 已复制");
        } catch (err) {
          toast("复制失败，请手动选择文本", true);
        }
      });

    const downloadBtn = document.getElementById("download-report");
    if (downloadBtn)
      downloadBtn.addEventListener("click", () => {
        const blob = new Blob([report.markdown], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `litmemory-周报-${report.week_start}.md`;
        anchor.click();
        URL.revokeObjectURL(url);
      });

    if (!state.report && hashQuery().get("auto")) {
      document.getElementById("make-report").click();
    }
  }

  function markdown(text) {
    const lines = String(text || "").split("\n");
    const out = [];
    let listOpen = false;
    const closeList = () => {
      if (listOpen) {
        out.push("</ul>");
        listOpen = false;
      }
    };
    const inline = (value) =>
      esc(value)
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    lines.forEach((line) => {
      const raw = line.replace(/\s+$/, "");
      if (!raw.trim()) {
        closeList();
        return;
      }
      if (/^#{1,3}\s/.test(raw)) {
        closeList();
        const level = raw.match(/^#+/)[0].length;
        out.push(`<h${level}>${inline(raw.replace(/^#+\s*/, ""))}</h${level}>`);
        return;
      }
      if (/^>\s?/.test(raw)) {
        closeList();
        out.push(`<blockquote>${inline(raw.replace(/^>\s?/, ""))}</blockquote>`);
        return;
      }
      if (/^---+$/.test(raw)) {
        closeList();
        out.push("<hr>");
        return;
      }
      const item = raw.match(/^\s*[-*]\s+(.*)$/);
      if (item) {
        if (!listOpen) {
          out.push("<ul>");
          listOpen = true;
        }
        const body = item[1].replace(/^\[[ xX]\]\s*/, (m) => (m.toLowerCase().includes("x") ? "☑ " : "☐ "));
        out.push(`<li>${inline(body)}</li>`);
        return;
      }
      closeList();
      out.push(`<p>${inline(raw)}</p>`);
    });
    closeList();
    return out.join("\n");
  }

  /* ------------------------------------------------------------------- init */
  document.getElementById("menu-btn").addEventListener("click", () => {
    document.body.classList.toggle("nav-open");
  });
  modal().addEventListener("click", (event) => {
    if (event.target === modal()) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal().hidden) closeModal();
  });

  window.addEventListener("hashchange", navigate);
  (async () => {
    await loadBootstrap();
    try {
      state.health = await api("/api/health");
    } catch (err) {
      state.health = null;
    }
    await navigate();
    renderStatus();
  })();
})();
