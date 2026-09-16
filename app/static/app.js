const TYPE_LABELS = {
  choice: "选择题",
  short_answer: "简答题",
  essay: "论述题",
  case_analysis: "案例分析",
  other: "其他",
};

const state = {
  questions: [],
  index: 0,
  answerVisible: false,
};

const els = {
  subject: document.getElementById("subject"),
  year: document.getElementById("year"),
  type: document.getElementById("type"),
  source: document.getElementById("source"),
  count: document.getElementById("count"),
  startBtn: document.getElementById("startBtn"),
  keyword: document.getElementById("keyword"),
  searchBtn: document.getElementById("searchBtn"),
  quiz: document.getElementById("quiz"),
  results: document.getElementById("results"),
  resultsList: document.getElementById("resultsList"),
  card: document.getElementById("card"),
  progress: document.getElementById("progress"),
  progressPct: document.getElementById("progressPct"),
  progressFill: document.getElementById("progressFill"),
  revealBtn: document.getElementById("revealBtn"),
  prevBtn: document.getElementById("prevBtn"),
  nextBtn: document.getElementById("nextBtn"),
  message: document.getElementById("message"),
  stats: document.getElementById("stats"),
};

function apiBase() {
  const path = window.location.pathname.replace(/\/$/, "");
  if (!path || path === "/index.html") return "";
  return path;
}

async function api(path) {
  const url = `${apiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败 (${res.status})`);
  }
  return res.json();
}

function setMessage(text, isError = false) {
  els.message.textContent = text;
  els.message.classList.toggle("error", isError);
}

function updateProgress() {
  const total = state.questions.length;
  const current = state.index + 1;
  const pct = total ? Math.round((current / total) * 100) : 0;
  els.progress.textContent = `第 ${current} / ${total} 题`;
  els.progressPct.textContent = `${pct}%`;
  els.progressFill.style.width = `${pct}%`;
}

function renderQuestion() {
  const q = state.questions[state.index];
  if (!q) return;

  state.answerVisible = false;
  updateProgress();
  els.revealBtn.textContent = "显示答案";
  els.revealBtn.disabled = false;

  const optionsHtml = q.options
    ? Object.keys(q.options)
        .sort()
        .map(
          (key) => `
          <div class="option">
            <span class="option-key">${key}</span>
            <span class="option-text">${escapeHtml(q.options[key])}</span>
          </div>`
        )
        .join("")
    : "";

  const sourceClass = q.source === "bb" ? "bb" : "";
  els.card.innerHTML = `
    <div class="meta">
      <span class="tag">${escapeHtml(q.subject)}</span>
      <span class="tag">${q.year} 年</span>
      <span class="tag">第 ${q.number} 题</span>
      <span class="tag tag-type">${TYPE_LABELS[q.question_type] || q.question_type}</span>
      <span class="tag tag-source ${sourceClass}">${escapeHtml(q.source_label || "未知来源")}</span>
    </div>
    <div class="stem">${escapeHtml(q.stem)}</div>
    ${optionsHtml ? `<div class="options">${optionsHtml}</div>` : ""}
    <div id="answerBox" class="answer hidden"></div>
  `;

  els.prevBtn.disabled = state.index === 0;
  els.nextBtn.textContent = state.index === state.questions.length - 1 ? "完成练习 ✓" : "下一题 →";
}

function showAnswer() {
  const q = state.questions[state.index];
  const box = document.getElementById("answerBox");
  if (!box) return;

  if (!q.answer) {
    box.innerHTML = `<span class="answer-label">参考答案</span>暂无答案`;
  } else {
    box.innerHTML = `<span class="answer-label">参考答案</span>${escapeHtml(q.answer)}`;
  }
  box.classList.remove("hidden");
  state.answerVisible = true;
  els.revealBtn.textContent = "已显示";
  els.revealBtn.disabled = true;
}

function renderResults(items) {
  els.quiz.classList.add("hidden");
  els.results.classList.remove("hidden");
  els.resultsList.innerHTML = items.length
    ? items
        .map(
          (q) => `
        <article class="result-item">
          <div class="meta">
            <span class="tag">${escapeHtml(q.subject)}</span>
            <span class="tag">${q.year} 年</span>
            <span class="tag">#${q.number}</span>
          </div>
          <div class="stem">${escapeHtml(q.stem.slice(0, 200))}${q.stem.length > 200 ? "…" : ""}</div>
        </article>`
        )
        .join("")
    : `<p class="message">未找到匹配题目</p>`;
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function loadFilters() {
  const subjects = await api("/api/subjects");
  subjects.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    els.subject.appendChild(opt);
  });
  await refreshYears();
}

function filterParams() {
  const params = new URLSearchParams();
  if (els.subject.value) params.set("subject", els.subject.value);
  if (els.source.value) params.set("source", els.source.value);
  return params;
}

async function refreshYears() {
  const params = filterParams();
  const qs = params.toString();
  const years = await api(`/api/years${qs ? `?${qs}` : ""}`);
  els.year.innerHTML = '<option value="">全部</option>';
  years.forEach((year) => {
    const opt = document.createElement("option");
    opt.value = year;
    opt.textContent = `${year} 年`;
    els.year.appendChild(opt);
  });
}

async function loadStats() {
  const params = filterParams();
  const qs = params.toString();
  const stats = await api(`/api/stats${qs ? `?${qs}` : ""}`);
  const grouped = {};

  for (const item of stats) {
    if (!grouped[item.subject]) grouped[item.subject] = [];
    grouped[item.subject].push(item);
  }

  els.stats.innerHTML = Object.entries(grouped)
    .map(([subject, rows]) => {
      const sorted = rows.sort((a, b) => b.year - a.year || a.source.localeCompare(b.source));
      const rowHtml = sorted
        .map((item) => {
          const badgeClass = item.source === "bb" ? "bb" : "web";
          const badgeText = item.source === "bb" ? "bb" : "网";
          return `
            <div class="stat-row">
              <span class="stat-year">${item.year} 年<span class="stat-badge ${badgeClass}">${badgeText}</span></span>
              <span class="stat-count">${item.total} 题</span>
            </div>`;
        })
        .join("");
      return `
        <div class="stat-group">
          <div class="stat-group-title">${escapeHtml(subject)}</div>
          <div class="stat-rows">${rowHtml}</div>
        </div>`;
    })
    .join("");
}

async function startQuiz() {
  const params = new URLSearchParams();
  params.set("count", els.count.value || "10");
  if (els.subject.value) params.set("subject", els.subject.value);
  if (els.year.value) params.set("year", els.year.value);
  if (els.type.value) params.set("question_type", els.type.value);
  if (els.source.value) params.set("source", els.source.value);

  try {
    const questions = await api(`/api/questions/random?${params}`);
    state.questions = questions;
    state.index = 0;
    els.results.classList.add("hidden");
    els.quiz.classList.remove("hidden");
    renderQuestion();
    setMessage("");
    els.quiz.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setMessage(err.message, true);
  }
}

async function searchQuestions() {
  const keyword = els.keyword.value.trim();
  if (!keyword) return;
  const params = new URLSearchParams({ keyword, limit: "20" });
  if (els.subject.value) params.set("subject", els.subject.value);
  if (els.year.value) params.set("year", els.year.value);
  if (els.source.value) params.set("source", els.source.value);

  try {
    const items = await api(`/api/questions/search?${params}`);
    renderResults(items);
    setMessage(`找到 ${items.length} 条结果`);
    els.results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setMessage(err.message, true);
  }
}

async function onFilterChange() {
  await refreshYears();
  await loadStats();
}

els.subject.addEventListener("change", onFilterChange);
els.source.addEventListener("change", onFilterChange);
els.startBtn.addEventListener("click", startQuiz);
els.searchBtn.addEventListener("click", searchQuestions);
els.keyword.addEventListener("keydown", (e) => {
  if (e.key === "Enter") searchQuestions();
});
els.revealBtn.addEventListener("click", () => {
  if (!state.answerVisible) showAnswer();
});
els.prevBtn.addEventListener("click", () => {
  if (state.index > 0) {
    state.index -= 1;
    renderQuestion();
  }
});
els.nextBtn.addEventListener("click", () => {
  if (state.index < state.questions.length - 1) {
    state.index += 1;
    renderQuestion();
  } else {
    setMessage("本轮练习完成，可调整条件重新开始。");
  }
});

loadFilters().then(loadStats).catch((err) => setMessage(err.message, true));
