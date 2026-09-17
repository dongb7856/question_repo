const TYPE_LABELS = {
  choice: "选择题",
  short_answer: "简答题",
  essay: "论述题",
  case_analysis: "案例分析",
  other: "其他",
};

const ENGLISH_SECTION_LABELS = {
  phonetics: "语音题",
  vocabulary: "词汇和语法",
  cloze: "完形填空",
  reading: "阅读理解",
  dialogue: "日常对话",
  writing: "写作",
};

const GENERIC_TYPE_OPTIONS = [
  { value: "choice", label: "选择题" },
  { value: "short_answer", label: "简答题" },
  { value: "essay", label: "论述题" },
  { value: "case_analysis", label: "案例分析" },
];

const ENGLISH_TYPE_OPTIONS = [
  { value: "phonetics", label: "语音题" },
  { value: "vocabulary", label: "词汇和语法" },
  { value: "cloze", label: "完形填空" },
  { value: "reading", label: "阅读理解" },
  { value: "dialogue", label: "日常对话" },
  { value: "writing", label: "写作" },
];

const state = {
  questions: [],
  index: 0,
  answerVisible: false,
  selectedAnswer: null,
  answered: false,
  aiAvailable: false,
  aiLoading: false,
  analyzeRequestId: 0,
  attempts: [],
  sessionStartedAt: null,
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
  quizSummary: document.getElementById("quizSummary"),
  summaryContent: document.getElementById("summaryContent"),
  restartBtn: document.getElementById("restartBtn"),
};

function apiBase() {
  const path = window.location.pathname.replace(/\/$/, "");
  if (!path || path === "/index.html") return "";
  return path;
}

async function api(path, options = {}) {
  const url = `${apiBase()}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, options);
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

function inferEnglishSection(q) {
  if (isGroupSet(q)) return q.groupKind;
  const stem = q?.stem || "";
  const sec = q?.section_title || "";
  if (stem.includes("【完形短文】")) return "cloze";
  if (stem.includes("【阅读材料】")) return "reading";
  if (stem.includes("【对话材料】")) return "dialogue";
  if (/Writing|作文/i.test(sec) || /write an essay|写一篇|写一封/i.test(stem)) return "writing";
  if (/语音|Phonetics/i.test(sec)) return "phonetics";
  if (/Vocabulary|词汇|语法|Structure/i.test(sec)) return "vocabulary";
  if (q?.number <= 5 && !stem.includes("【")) return "phonetics";
  if (q?.number <= 20 && q?.question_type === "choice" && !stem.includes("【")) return "vocabulary";
  return null;
}

function questionDisplayType(q) {
  if (!q) return "题目";
  const englishSection = inferEnglishSection(q);
  if (englishSection) return ENGLISH_SECTION_LABELS[englishSection] || englishSection;
  return TYPE_LABELS[q.question_type] || q.question_type || "题目";
}

function refreshTypeOptions() {
  const subject = els.subject.value;
  const previous = els.type.value;
  const options =
    subject === "英语"
      ? ENGLISH_TYPE_OPTIONS
      : subject === "政治" || subject === "民法"
        ? GENERIC_TYPE_OPTIONS
        : [];

  els.type.innerHTML = '<option value="">全部</option>';
  options.forEach(({ value, label }) => {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = label;
    els.type.appendChild(opt);
  });

  const valid = ["", ...options.map((item) => item.value)];
  els.type.value = valid.includes(previous) ? previous : "";
}

function appendTypeFilter(params) {
  const value = els.type.value;
  if (!value) return;
  if (els.subject.value === "英语") {
    params.set("english_section", value);
  } else {
    params.set("question_type", value);
  }
}

function parseOptions(raw) {
  if (!raw) return null;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }
  return typeof raw === "object" ? raw : null;
}

const GROUP_CONFIG = {
  cloze: {
    materialTag: "【完形短文】",
    sectionRe: /完形|完型|Cloze/i,
    typeName: "完形填空",
    unit: "空",
    stripPrefix: /^【完形短文】\n?/,
    maxLetter: "D",
  },
  reading: {
    materialTag: "【阅读材料】",
    sectionRe: /阅读|Reading/i,
    typeName: "阅读理解",
    unit: "题",
    stripPrefix: /^【阅读材料】\n?/,
    maxLetter: "D",
  },
  dialogue: {
    materialTag: "【对话材料】",
    sectionRe: /日常对话|Daily\s+Conversation/i,
    typeName: "日常对话",
    unit: "空",
    stripPrefix: /^【对话材料】\n?/,
    maxLetter: "H",
  },
};

function splitMaterialStem(stem) {
  const marker = "\n\n【题目】\n";
  const idx = (stem || "").indexOf(marker);
  if (idx === -1) return ["", stem || ""];
  return [stem.slice(0, idx), stem.slice(idx + marker.length).trim()];
}

function getMaterialPassageKey(q, config) {
  const stem = q?.stem || "";
  if (!stem.includes(config.materialTag)) return null;
  if (!config.sectionRe.test(q.section_title || "")) return null;
  const [passage] = splitMaterialStem(stem);
  return passage || null;
}

function parseChoicePoolFromPassage(passage) {
  const options = {};
  for (const line of passage.split("\n")) {
    const match = line.trim().match(/^([A-H])[\.．、]\s*(.+)$/);
    if (match) options[match[1]] = match[2].trim();
  }
  if (Object.keys(options).length >= 4) return options;
  const inline = passage.replace(/\n/g, " ");
  for (const match of inline.matchAll(/([A-H])[\.．、]\s*(.+?)(?=\s+[A-H][\.．、]|$)/g)) {
    if (!options[match[1]]) options[match[1]] = match[2].trim();
  }
  return Object.keys(options).length >= 4 ? options : null;
}

function parseItemId(kind, prompt, number) {
  if (kind === "cloze") {
    const match = String(prompt || "").match(/【(C\d+)】/);
    return match ? match[1] : String(number);
  }
  return String(number);
}

function buildGroupComposite(group, passageKey, kind) {
  const config = GROUP_CONFIG[kind];
  const sorted = [...group].sort((a, b) => a.number - b.number);
  const pool = kind === "dialogue" ? parseChoicePoolFromPassage(passageKey) : null;
  const groupItems = sorted.map((q) => {
    const [, prompt] = splitMaterialStem(q.stem || "");
    const itemId = parseItemId(kind, prompt, q.number);
    return {
      id: q.id,
      number: q.number,
      itemId,
      label: kind === "reading" ? `第 ${q.number} 题` : prompt,
      prompt,
      options: parseOptions(q.options) || pool,
      answer: normalizeAnswerKey(q.answer, config.maxLetter),
    };
  });
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  return {
    ...first,
    id: sorted.map((item) => item.id).join(","),
    groupKind: kind,
    groupItems,
    choicePool: pool,
    stem: passageKey,
    number: `${first.number}–${last.number}`,
    options: null,
    answer: null,
    explanation: null,
  };
}

function groupByMaterialKind(questions, kind) {
  const config = GROUP_CONFIG[kind];
  const grouped = [];
  const used = new Set();

  for (let i = 0; i < questions.length; i += 1) {
    if (used.has(i)) continue;
    const q = questions[i];
    if (q.groupKind) {
      grouped.push(q);
      continue;
    }
    const key = getMaterialPassageKey(q, config);
    if (!key) {
      grouped.push(q);
      continue;
    }
    const mates = [q];
    used.add(i);
    for (let j = i + 1; j < questions.length; j += 1) {
      if (used.has(j)) continue;
      const other = questions[j];
      if (other.groupKind) continue;
      if (getMaterialPassageKey(other, config) === key) {
        mates.push(other);
        used.add(j);
      }
    }
    grouped.push(mates.length > 1 ? buildGroupComposite(mates, key, kind) : q);
  }
  return grouped;
}

function groupMaterialQuestions(questions) {
  let result = questions;
  for (const kind of ["cloze", "reading", "dialogue"]) {
    result = groupByMaterialKind(result, kind);
  }
  return result;
}

function isGroupSet(q) {
  return Boolean(q?.groupKind && Array.isArray(q.groupItems) && q.groupItems.length > 1);
}

function isClozeSet(q) {
  return isGroupSet(q) && q.groupKind === "cloze";
}

function getGroupConfig(q) {
  return GROUP_CONFIG[q?.groupKind] || null;
}

// 兼容旧引用
function getClozePassageKey(q) {
  return getMaterialPassageKey(q, GROUP_CONFIG.cloze);
}

function groupClozeQuestions(questions) {
  return groupMaterialQuestions(questions);
}

function isChoiceQuestion(q) {
  if (isGroupSet(q)) return false;
  const options = parseOptions(q.options);
  if (!options) return false;
  const keys = Object.keys(options);
  return keys.length >= 2 && keys.some((key) => /^[A-D]$/i.test(key));
}

function normalizeAnswer(raw) {
  return normalizeAnswerKey(raw, "D");
}

function normalizeAnswerKey(raw, maxLetter = "D") {
  if (!raw) return null;
  const pattern = maxLetter === "H" ? /^([A-H])/i : /^([A-D])/i;
  const match = String(raw).trim().match(pattern);
  return match ? match[1].toUpperCase() : null;
}

function formatAnswerText(raw) {
  if (!raw) return "暂无";
  return escapeHtml(String(raw));
}

function ensureAttempt(index) {
  if (!state.attempts[index]) {
    const q = state.questions[index];
    state.attempts[index] = {
      questionId: q?.id,
      subject: q?.subject,
      year: q?.year,
      number: q?.number,
      questionType: q?.question_type,
      stemPreview: q?.stem?.slice(0, 80) || "",
      isChoice: q ? isChoiceQuestion(q) : false,
      isGroupSet: q ? isGroupSet(q) : false,
      groupAnswers: {},
      userAnswer: null,
      storedAnswer: q?.answer || null,
      isCorrect: null,
      groupCorrect: null,
      groupGradable: null,
      viewedAnswer: false,
      deepseekAgrees: null,
      deepseekSuggested: null,
      deepseekAnalysis: "",
      deepseekDiscrepancy: "",
      similarityScore: null,
      groupDeepseekItems: {},
    };
  }
  return state.attempts[index];
}

function allGroupItemsAnswered(q, answers) {
  if (!isGroupSet(q)) return false;
  return q.groupItems.every((item) => Boolean(answers?.[item.itemId]));
}

function snapshotCurrentAttempt() {
  const q = state.questions[state.index];
  if (!q) return;
  const attempt = ensureAttempt(state.index);
  attempt.viewedAnswer = state.answerVisible;
  attempt.storedAnswer = q.answer || null;

  if (isGroupSet(q)) {
    attempt.groupAnswers = { ...(state.groupAnswers || {}) };
    if (state.answerVisible) {
      const stats = gradeGroupSet(q, attempt.groupAnswers);
      attempt.groupCorrect = stats.correct;
      attempt.groupGradable = stats.gradable;
      attempt.isCorrect = stats.gradable > 0 && stats.correct === stats.gradable;
    }
    return;
  }

  attempt.userAnswer = state.selectedAnswer;
  if (attempt.isChoice && normalizeAnswer(q.answer) && state.selectedAnswer) {
    attempt.isCorrect = normalizeAnswer(q.answer) === state.selectedAnswer;
  }
}

function gradeGroupSet(q, answers) {
  let correct = 0;
  let gradable = 0;
  for (const item of q.groupItems) {
    if (!item.answer) continue;
    gradable += 1;
    if (answers?.[item.itemId] === item.answer) correct += 1;
  }
  return { correct, gradable };
}

function formatGroupAnswerKey(q) {
  return q.groupItems
    .filter((item) => item.answer)
    .map((item) => {
      if (q.groupKind === "reading") return `${item.number}: ${item.answer}`;
      return `${item.label}: ${item.answer}`;
    })
    .join("；");
}

function groupResultLabel(q) {
  const config = getGroupConfig(q);
  return config?.typeName || "题目";
}

function restoreAttempt(index) {
  const attempt = state.attempts[index];
  if (!attempt) return;

  state.selectedAnswer = attempt.userAnswer;
  state.groupAnswers = { ...(attempt.groupAnswers || {}) };
  state.answered = Boolean(
    attempt.userAnswer || attempt.viewedAnswer || Object.keys(state.groupAnswers).length
  );
  state.answerVisible = attempt.viewedAnswer;

  if (!attempt.viewedAnswer && !attempt.userAnswer && !Object.keys(state.groupAnswers).length) {
    return;
  }

  const q = state.questions[index];
  if (!q) return;

  if (isGroupSet(q)) {
    applyGroupSelectionStyles(q, state.groupAnswers);
    if (attempt.viewedAnswer) {
      applyGroupAnswerStyles(q, state.groupAnswers);
      const stats = gradeGroupSet(q, state.groupAnswers);
      const config = getGroupConfig(q);
      const resultHtml = stats.gradable
        ? `<div class="answer-result ${stats.correct === stats.gradable ? "correct" : "incorrect"}">${escapeHtml(groupResultLabel(q))}：答对 ${stats.correct} / ${stats.gradable} ${config?.unit || "题"}</div>`
        : `<div class="answer-result muted">本题暂无完整标准答案</div>`;
      revealAnswerPanel(resultHtml, { restoreDeepseek: attempt });
      els.revealBtn.textContent = "已显示";
      els.revealBtn.disabled = true;
    }
    return;
  }

  if (attempt.isChoice && attempt.userAnswer) {
    const correctKey = normalizeAnswer(q.answer);
    const isCorrect = attempt.isCorrect;
    els.card.querySelectorAll(".option").forEach((el) => {
      const optionKey = el.dataset.key;
      el.classList.add("disabled");
      if (optionKey === attempt.userAnswer) {
        el.classList.add(isCorrect ? "correct" : "incorrect");
      } else if (!isCorrect && optionKey === correctKey) {
        el.classList.add("correct");
      }
    });

    let resultHtml = "";
    if (!correctKey) {
      resultHtml = `<div class="answer-result muted">你选择了 ${attempt.userAnswer}，题库暂无标准答案，无法判定对错</div>`;
    } else if (isCorrect) {
      resultHtml = `<div class="answer-result correct">✓ 你选择了 ${attempt.userAnswer}，与题库参考答案一致</div>`;
    } else {
      resultHtml = `<div class="answer-result incorrect">✗ 你选择了 ${attempt.userAnswer}，题库参考答案是 ${correctKey}</div>`;
    }
    revealAnswerPanel(resultHtml, { restoreDeepseek: attempt });
    els.revealBtn.disabled = true;
    return;
  }

  if (attempt.viewedAnswer) {
    revealAnswerPanel("", { restoreDeepseek: attempt });
    els.revealBtn.textContent = "已显示";
    els.revealBtn.disabled = true;
  }
}

function formatDuration(ms) {
  const totalSec = Math.max(0, Math.round(ms / 1000));
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  if (min <= 0) return `${sec} 秒`;
  return `${min} 分 ${sec} 秒`;
}

function computeSummary() {
  const total = state.questions.length;
  let choiceAnswered = 0;
  let choiceCorrect = 0;
  let choiceWrong = 0;
  let choiceSkipped = 0;
  let subjectiveTotal = 0;
  let subjectiveViewed = 0;
  let skipped = 0;
  let deepseekChecked = 0;
  let deepseekDisagree = 0;
  let similarityTotal = 0;
  let similarityCount = 0;
  const wrongItems = [];
  const disagreeItems = [];

  for (let i = 0; i < total; i += 1) {
    const q = state.questions[i];
    const attempt = state.attempts[i] || ensureAttempt(i);
    const gradableChoice = attempt.isChoice && normalizeAnswer(q.answer);
    const gradableGroup = attempt.isGroupSet && attempt.groupGradable;

    if (gradableGroup) {
      if (attempt.viewedAnswer) {
        choiceAnswered += 1;
        if (attempt.isCorrect) choiceCorrect += 1;
        else {
          choiceWrong += 1;
          wrongItems.push({
            subject: q.subject,
            year: q.year,
            number: q.number,
            userAnswer: `${attempt.groupCorrect}/${attempt.groupGradable}`,
            storedAnswer: `${attempt.groupGradable}/${attempt.groupGradable}`,
            stem: q.stem,
          });
        }
      } else if (Object.keys(attempt.groupAnswers || {}).length) {
        choiceSkipped += 1;
        skipped += 1;
      } else {
        choiceSkipped += 1;
        skipped += 1;
      }
    } else if (gradableChoice) {
      if (attempt.userAnswer) {
        choiceAnswered += 1;
        if (attempt.isCorrect) choiceCorrect += 1;
        else {
          choiceWrong += 1;
          wrongItems.push({
            subject: q.subject,
            year: q.year,
            number: q.number,
            userAnswer: attempt.userAnswer,
            storedAnswer: normalizeAnswer(q.answer),
            stem: q.stem,
          });
        }
      } else {
        choiceSkipped += 1;
        skipped += 1;
      }
    } else if (attempt.isChoice) {
      skipped += 1;
    } else {
      subjectiveTotal += 1;
      if (attempt.viewedAnswer) subjectiveViewed += 1;
      else skipped += 1;
    }

    if (attempt.isGroupSet && attempt.groupDeepseekItems) {
      for (const item of q.groupItems) {
        const ds = attempt.groupDeepseekItems[item.itemId];
        if (!ds || (ds.deepseekAgrees !== true && ds.deepseekAgrees !== false)) continue;
        deepseekChecked += 1;
        if (ds.deepseekAgrees === false) {
          deepseekDisagree += 1;
          disagreeItems.push({
            subject: q.subject,
            year: q.year,
            number: item.number ?? q.number,
            storedAnswer: item.answer,
            suggestedAnswer: ds.deepseekSuggested,
            similarityScore: ds.similarityScore,
            stem: item.prompt || q.stem,
          });
        }
        if (ds.similarityScore !== null && ds.similarityScore !== undefined) {
          similarityTotal += ds.similarityScore;
          similarityCount += 1;
        }
      }
    } else if (attempt.deepseekAgrees === true || attempt.deepseekAgrees === false) {
      deepseekChecked += 1;
      if (attempt.deepseekAgrees === false) {
        deepseekDisagree += 1;
        disagreeItems.push({
          subject: q.subject,
          year: q.year,
          number: q.number,
          storedAnswer: q.answer,
          suggestedAnswer: attempt.deepseekSuggested,
          similarityScore: attempt.similarityScore,
          stem: q.stem,
        });
      }
      if (attempt.similarityScore !== null && attempt.similarityScore !== undefined) {
        similarityTotal += attempt.similarityScore;
        similarityCount += 1;
      }
    }
  }

  const accuracy = choiceAnswered ? Math.round((choiceCorrect / choiceAnswered) * 100) : null;
  const avgSimilarity = similarityCount ? Math.round(similarityTotal / similarityCount) : null;
  const durationMs = state.sessionStartedAt ? Date.now() - state.sessionStartedAt : 0;

  return {
    total,
    choiceAnswered,
    choiceCorrect,
    choiceWrong,
    choiceSkipped,
    subjectiveTotal,
    subjectiveViewed,
    skipped,
    accuracy,
    deepseekChecked,
    deepseekDisagree,
    avgSimilarity,
    wrongItems,
    disagreeItems,
    durationMs,
  };
}

function ensureSummaryElements() {
  if (els.quizSummary && els.summaryContent && els.restartBtn) return;

  const page = document.querySelector(".page");
  if (!page) return;

  const section = document.createElement("section");
  section.id = "quizSummary";
  section.className = "panel quiz-summary hidden";
  section.innerHTML = `
    <div class="section-head">
      <h2>练习汇总</h2>
      <span class="hint">基于本轮作答与 DeepSeek 对比</span>
    </div>
    <div id="summaryContent" class="summary-content"></div>
    <button id="restartBtn" class="btn btn-primary btn-restart">再练一轮</button>
  `;
  page.appendChild(section);

  els.quizSummary = section;
  els.summaryContent = section.querySelector("#summaryContent");
  els.restartBtn = section.querySelector("#restartBtn");
  els.restartBtn.addEventListener("click", () => {
    els.quizSummary.classList.add("hidden");
    setMessage("可调整条件后重新开始练习。");
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
}

function formatSimilarity(score) {
  if (score === null || score === undefined) return "";
  return `语义相似度 ${score}%`;
}

function renderSummaryList(title, items, className, renderItem) {
  if (!items.length) {
    return `
      <div class="summary-box">
        <h3>${escapeHtml(title)}</h3>
        <ul><li>无</li></ul>
      </div>`;
  }
  return `
    <div class="summary-box">
      <h3>${escapeHtml(title)}</h3>
      <div class="summary-list">
        ${items.map((item) => `<div class="summary-item ${className}">${renderItem(item)}</div>`).join("")}
      </div>
    </div>`;
}

function showQuizSummary() {
  snapshotCurrentAttempt();
  ensureSummaryElements();
  const summary = computeSummary();

  const accuracyText = summary.accuracy === null ? "—" : `${summary.accuracy}%`;
  const accuracyDetail =
    summary.choiceAnswered > 0
      ? `答对 ${summary.choiceCorrect} / 已作答 ${summary.choiceAnswered} 题`
      : "本轮没有可判对错的选择题";
  const similarityDetail =
    summary.avgSimilarity === null
      ? "暂无 DeepSeek 语义对比数据"
      : `平均语义相似度 ${summary.avgSimilarity}%（主观题看含义，不看字面）`;

  if (!els.quizSummary || !els.summaryContent) {
    setMessage(`练习完成：正确率 ${accuracyText}，DeepSeek 不一致 ${summary.deepseekDisagree} 题`, false);
    return;
  }

  els.quiz.classList.add("hidden");
  els.quizSummary.classList.remove("hidden");
  els.summaryContent.innerHTML = `
    <div class="summary-stats">
      <div class="summary-stat highlight">
        <div class="summary-stat-value">${accuracyText}</div>
        <div class="summary-stat-label">选择题正确率</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-value">${summary.choiceCorrect}</div>
        <div class="summary-stat-label">答对</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-value">${summary.choiceWrong}</div>
        <div class="summary-stat-label">答错</div>
      </div>
      <div class="summary-stat">
        <div class="summary-stat-value">${summary.total}</div>
        <div class="summary-stat-label">总题数</div>
      </div>
    </div>

    <div class="summary-breakdown">
      <div class="summary-box">
        <h3>作答情况</h3>
        <ul>
          <li>用时：${escapeHtml(formatDuration(summary.durationMs))}</li>
          <li>${escapeHtml(accuracyDetail)}</li>
          <li>主观题 ${summary.subjectiveTotal} 道，已查看答案 ${summary.subjectiveViewed} 道</li>
          <li>未作答 / 未查看 ${summary.skipped} 道</li>
        </ul>
      </div>
      <div class="summary-box">
        <h3>DeepSeek 对比</h3>
        <ul>
          <li>已分析 ${summary.deepseekChecked} 题</li>
          <li>与题库语义不一致 ${summary.deepseekDisagree} 题</li>
          <li>${escapeHtml(similarityDetail)}</li>
          <li>${summary.deepseekDisagree > 0 ? "建议重点核对不一致题目的题库答案" : "本轮 DeepSeek 与题库答案未发现明显冲突"}</li>
        </ul>
      </div>
    </div>

    <div class="summary-breakdown">
      ${renderSummaryList(
        "错题回顾",
        summary.wrongItems,
        "incorrect",
        (item) => `
          <div class="summary-item-head">
            <span class="tag">${escapeHtml(item.subject)}</span>
            <span class="tag">${item.year} 年</span>
            <span class="tag">第 ${item.number} 题</span>
          </div>
          <div class="summary-item-text">你选 ${escapeHtml(item.userAnswer)}，题库参考答案 ${escapeHtml(item.storedAnswer)}</div>
          <div class="summary-item-text">${escapeHtml(item.stem.slice(0, 100))}${item.stem.length > 100 ? "…" : ""}</div>`
      )}
      ${renderSummaryList(
        "DeepSeek 质疑题库答案",
        summary.disagreeItems,
        "disagree",
        (item) => `
          <div class="summary-item-head">
            <span class="tag">${escapeHtml(item.subject)}</span>
            <span class="tag">${item.year} 年</span>
            <span class="tag">第 ${item.number} 题</span>
          </div>
          <div class="summary-item-text">题库 ${escapeHtml(item.storedAnswer || "暂无")} → DeepSeek 建议 ${escapeHtml(item.suggestedAnswer || "暂无")}${item.similarityScore !== null && item.similarityScore !== undefined ? `（${formatSimilarity(item.similarityScore)}）` : ""}</div>
          <div class="summary-item-text">${escapeHtml(item.stem.slice(0, 100))}${item.stem.length > 100 ? "…" : ""}</div>`
      )}
    </div>

    <div class="summary-box" id="aiSessionSummary">
      <h3>DeepSeek 汇总点评</h3>
      <p class="summary-item-text loading">正在生成本轮练习分析…</p>
    </div>
  `;

  setMessage("");
  els.quizSummary.scrollIntoView({ behavior: "smooth", block: "start" });
  loadSessionSummary(summary);
}

async function loadSessionSummary(summary) {
  const box = document.getElementById("aiSessionSummary");
  if (!box || !state.aiAvailable) {
    if (box) {
      box.innerHTML = "<h3>DeepSeek 汇总点评</h3><p class=\"summary-item-text muted\">未配置 DeepSeek</p>";
    }
    return;
  }

  try {
    const payload = {
      total: summary.total,
      choice_answered: summary.choiceAnswered,
      choice_correct: summary.choiceCorrect,
      choice_wrong: summary.choiceWrong,
      accuracy: summary.accuracy,
      subjective_total: summary.subjectiveTotal,
      subjective_viewed: summary.subjectiveViewed,
      skipped: summary.skipped,
      deepseek_checked: summary.deepseekChecked,
      deepseek_disagree: summary.deepseekDisagree,
      avg_similarity: summary.avgSimilarity,
      duration_seconds: Math.round(summary.durationMs / 1000),
    };
    const result = await api("api/session/summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    box.innerHTML = `<h3>DeepSeek 汇总点评</h3><div class="analysis-text">${escapeHtml(result.summary).replaceAll("\n", "<br>")}</div>`;
  } catch (err) {
    box.innerHTML = `<h3>DeepSeek 汇总点评</h3><p class="summary-item-text">${escapeHtml(err.message)}</p>`;
  }
}

function buildComparePanel(q, resultHtml, options = {}) {
  const storedAnswer = isGroupSet(q)
    ? formatGroupAnswerKey(q)
    : q.answer;
  const storedAnswerHtml = storedAnswer
    ? `<div class="answer-col-value">${formatAnswerText(storedAnswer)}</div>`
    : `<div class="answer-col-value muted">暂无标准答案</div>`;
  const storedExplanation = q.explanation
    ? `<div class="explanation">${escapeHtml(q.explanation)}</div>`
    : "";

  const deepseekBody = !state.aiAvailable
    ? `<div class="answer-col-body muted">未配置 DeepSeek，无法对比分析</div>`
    : isGroupSet(q)
      ? `<div id="deepseekGroupAnalysis" class="answer-col-body group-deepseek-list loading">DeepSeek 逐题分析中…</div>`
      : `<div id="deepseekAnalysis" class="answer-col-body loading">DeepSeek 分析中…</div>`;

  return `
    ${resultHtml || ""}
    <div class="answer-compare">
      <div class="answer-col answer-col-stored">
        <div class="answer-col-head">
          <span class="answer-col-title">题库参考答案</span>
          <span class="answer-col-tag">来源标注</span>
        </div>
        ${storedAnswerHtml}
        ${storedExplanation}
      </div>
      <div class="answer-col answer-col-deepseek">
        <div class="answer-col-head">
          <span class="answer-col-title">DeepSeek 分析</span>
          <span id="deepseekBadge" class="answer-col-tag hidden"></span>
        </div>
        <div id="deepseekSuggested" class="answer-col-value hidden"></div>
        ${deepseekBody}
      </div>
    </div>
  `;
}

function renderDeepSeekAnalysis(data) {
  const suggestedEl = document.getElementById("deepseekSuggested");
  const analysisEl = document.getElementById("deepseekAnalysis");
  const badgeEl = document.getElementById("deepseekBadge");
  const deepseekCol = document.querySelector(".answer-col-deepseek");
  if (!analysisEl) return;

  analysisEl.classList.remove("loading");
  const attempt = ensureAttempt(state.index);
  attempt.deepseekAgrees = data.agrees_with_stored;
  attempt.deepseekSuggested = data.suggested_answer || null;
  attempt.deepseekAnalysis = data.analysis || "";
  attempt.deepseekDiscrepancy = data.discrepancy_note || "";
  attempt.similarityScore = data.similarity_score ?? null;

  if (suggestedEl) {
    suggestedEl.classList.remove("hidden");
    suggestedEl.textContent = data.suggested_answer || "未能给出明确答案";
  }

  let html = `<div class="analysis-text">${escapeHtml(data.analysis || "暂无解析").replaceAll("\n", "<br>")}</div>`;
  if (data.discrepancy_note) {
    html += `<div class="discrepancy-note">${escapeHtml(data.discrepancy_note).replaceAll("\n", "<br>")}</div>`;
  }
  analysisEl.innerHTML = html;

  if (badgeEl && deepseekCol) {
    deepseekCol.classList.remove("agree", "disagree");
    const similarityText = formatSimilarity(data.similarity_score);
    if (data.agrees_with_stored) {
      badgeEl.textContent = similarityText ? `含义一致 · ${similarityText}` : "与题库一致";
      badgeEl.className = "answer-col-tag tag-agree";
      deepseekCol.classList.add("agree");
    } else {
      badgeEl.textContent = similarityText ? `含义不一致 · ${similarityText}` : "与题库不一致";
      badgeEl.className = "answer-col-tag tag-disagree";
      deepseekCol.classList.add("disagree");
    }
    badgeEl.classList.remove("hidden");
  }
}

function renderDeepSeekError(message) {
  const analysisEl = document.getElementById("deepseekAnalysis");
  const badgeEl = document.getElementById("deepseekBadge");
  if (!analysisEl) return;
  analysisEl.classList.remove("loading");
  analysisEl.innerHTML = `<div class="analysis-error">${escapeHtml(message)}</div>`;
  if (badgeEl) {
    badgeEl.textContent = "分析失败";
    badgeEl.className = "answer-col-tag tag-error";
    badgeEl.classList.remove("hidden");
  }
}

function groupDeepseekItemHtml(item, data) {
  const agrees = data.agrees_with_stored ?? data.deepseekAgrees;
  const suggested = data.suggested_answer ?? data.deepseekSuggested ?? "";
  const analysis = data.analysis ?? data.deepseekAnalysis ?? "";
  const discrepancy = data.discrepancy_note ?? data.deepseekDiscrepancy ?? "";
  const similarity = data.similarity_score ?? data.similarityScore;
  const tagClass = agrees ? "tag-agree" : "tag-disagree";
  const tagText = agrees
    ? formatSimilarity(similarity)
      ? `一致 · ${formatSimilarity(similarity)}`
      : "与题库一致"
    : formatSimilarity(similarity)
      ? `不一致 · ${formatSimilarity(similarity)}`
      : "与题库不一致";

  let body = `<div class="group-deepseek-suggested">建议答案：${escapeHtml(suggested || "未能给出")}</div>`;
  body += `<div class="analysis-text">${escapeHtml(analysis || "暂无解析").replaceAll("\n", "<br>")}</div>`;
  if (discrepancy) {
    body += `<div class="discrepancy-note">${escapeHtml(discrepancy).replaceAll("\n", "<br>")}</div>`;
  }

  return `
    <article class="group-deepseek-item ${agrees ? "agree" : "disagree"}" data-item="${escapeHtml(item.itemId)}">
      <div class="group-deepseek-head">
        <span class="group-deepseek-label">${escapeHtml(item.label)}</span>
        <span class="answer-col-tag ${tagClass}">${tagText}</span>
      </div>
      <div class="group-deepseek-body">${body}</div>
    </article>`;
}

function updateGroupDeepseekBadge(itemsMap) {
  const badgeEl = document.getElementById("deepseekBadge");
  const deepseekCol = document.querySelector(".answer-col-deepseek");
  if (!badgeEl || !deepseekCol) return;

  const entries = Object.values(itemsMap || {}).filter(
    (item) => item.deepseekAgrees === true || item.deepseekAgrees === false
  );
  if (!entries.length) return;

  const agreeCount = entries.filter((item) => item.deepseekAgrees).length;
  const allAgree = agreeCount === entries.length;
  badgeEl.textContent = allAgree
    ? `全部一致 · ${agreeCount}/${entries.length}`
    : `部分不一致 · ${agreeCount}/${entries.length} 一致`;
  badgeEl.className = `answer-col-tag ${allAgree ? "tag-agree" : "tag-disagree"}`;
  badgeEl.classList.remove("hidden");
  deepseekCol.classList.toggle("agree", allAgree);
  deepseekCol.classList.toggle("disagree", !allAgree);
}

function renderDeepSeekGroupAnalysis(q, itemsMap) {
  const container = document.getElementById("deepseekGroupAnalysis");
  if (!container) return;

  container.classList.remove("loading");
  const gradableItems = q.groupItems.filter((item) => item.answer && item.id);
  if (!gradableItems.length) {
    container.innerHTML = `<div class="muted">本题暂无完整标准答案，无法逐题对比</div>`;
    return;
  }

  container.innerHTML = gradableItems
    .map((item) => {
      const stored = itemsMap?.[item.itemId];
      if (!stored) {
        return `
          <article class="group-deepseek-item" data-item="${escapeHtml(item.itemId)}">
            <div class="group-deepseek-head">
              <span class="group-deepseek-label">${escapeHtml(item.label)}</span>
            </div>
            <div class="group-deepseek-body muted">暂无分析结果</div>
          </article>`;
      }
      return groupDeepseekItemHtml(item, stored);
    })
    .join("");

  updateGroupDeepseekBadge(itemsMap);
}

async function loadDeepSeekGroupAnalysis(q) {
  if (!state.aiAvailable) return;

  const container = document.getElementById("deepseekGroupAnalysis");
  if (!container) return;

  const requestId = ++state.analyzeRequestId;
  state.aiLoading = true;
  const attempt = ensureAttempt(state.index);
  attempt.groupDeepseekItems = attempt.groupDeepseekItems || {};
  const answers = state.groupAnswers || {};
  const items = q.groupItems.filter((item) => item.answer && item.id && answers[item.itemId]);

  if (!items.length) {
    container.classList.remove("loading");
    container.innerHTML = `<div class="muted">无可分析子题</div>`;
    state.aiLoading = false;
    return;
  }

  container.innerHTML = items
    .map(
      (item) => `
      <article class="group-deepseek-item pending" data-item="${escapeHtml(item.itemId)}">
        <div class="group-deepseek-head">
          <span class="group-deepseek-label">${escapeHtml(item.label)}</span>
          <span class="answer-col-tag">分析中…</span>
        </div>
        <div class="group-deepseek-body loading">DeepSeek 分析中…</div>
      </article>`
    )
    .join("");

  try {
    await Promise.all(
      items.map(async (item) => {
        try {
          const data = await api(`api/questions/${item.id}/analyze`, { method: "POST" });
          if (requestId !== state.analyzeRequestId) return;
          attempt.groupDeepseekItems[item.itemId] = {
            deepseekAgrees: data.agrees_with_stored,
            deepseekSuggested: data.suggested_answer || null,
            deepseekAnalysis: data.analysis || "",
            deepseekDiscrepancy: data.discrepancy_note || "",
            similarityScore: data.similarity_score ?? null,
          };
          const row = container.querySelector(
            `.group-deepseek-item[data-item="${CSS.escape(item.itemId)}"]`
          );
          if (row) {
            row.outerHTML = groupDeepseekItemHtml(item, data);
          }
        } catch (err) {
          if (requestId !== state.analyzeRequestId) return;
          const row = container.querySelector(
            `.group-deepseek-item[data-item="${CSS.escape(item.itemId)}"]`
          );
          if (row) {
            row.classList.remove("pending");
            row.querySelector(".group-deepseek-body").innerHTML = `<div class="analysis-error">${escapeHtml(err.message)}</div>`;
            row.querySelector(".answer-col-tag").textContent = "分析失败";
            row.querySelector(".answer-col-tag").className = "answer-col-tag tag-error";
          }
        }
      })
    );
    if (requestId !== state.analyzeRequestId) return;
    updateGroupDeepseekBadge(attempt.groupDeepseekItems);
    snapshotCurrentAttempt();
  } finally {
    if (requestId === state.analyzeRequestId) {
      state.aiLoading = false;
    }
  }
}

async function loadDeepSeekAnalysis(questionId) {
  if (!state.aiAvailable) return;

  const requestId = ++state.analyzeRequestId;
  state.aiLoading = true;

  try {
    const data = await api(`api/questions/${questionId}/analyze`, { method: "POST" });
    if (requestId !== state.analyzeRequestId) return;
    renderDeepSeekAnalysis(data);
  } catch (err) {
    if (requestId !== state.analyzeRequestId) return;
    renderDeepSeekError(err.message);
  } finally {
    if (requestId === state.analyzeRequestId) {
      state.aiLoading = false;
    }
  }
}

function revealAnswerPanel(resultHtml, options = {}) {
  const q = state.questions[state.index];
  const box = document.getElementById("answerBox");
  if (!box || !q) return;

  box.className = "answer-panel";
  box.innerHTML = buildComparePanel(q, resultHtml, options);
  box.classList.remove("hidden");

  const attempt = options.restoreDeepseek;
  if (attempt) {
    if (isGroupSet(q) && attempt.groupDeepseekItems && Object.keys(attempt.groupDeepseekItems).length) {
      renderDeepSeekGroupAnalysis(q, attempt.groupDeepseekItems);
      return;
    }
    if (!isGroupSet(q) && (attempt.deepseekAgrees === true || attempt.deepseekAgrees === false)) {
      renderDeepSeekAnalysis({
        suggested_answer: attempt.deepseekSuggested,
        analysis: attempt.deepseekAnalysis || "",
        discrepancy_note: attempt.deepseekDiscrepancy || "",
        agrees_with_stored: attempt.deepseekAgrees,
        similarity_score: attempt.similarityScore,
      });
      return;
    }
  }

  if (isGroupSet(q)) {
    loadDeepSeekGroupAnalysis(q);
    return;
  }

  loadDeepSeekAnalysis(q.id);
}

function revealGroupAnswer() {
  const q = state.questions[state.index];
  if (!q || !isGroupSet(q)) return;

  state.answerVisible = true;
  applyGroupAnswerStyles(q, state.groupAnswers || {});
  const stats = gradeGroupSet(q, state.groupAnswers || {});
  const config = getGroupConfig(q);
  snapshotCurrentAttempt();
  const resultHtml = stats.gradable
    ? `<div class="answer-result ${stats.correct === stats.gradable ? "correct" : "incorrect"}">${escapeHtml(groupResultLabel(q))}：答对 ${stats.correct} / ${stats.gradable} ${config?.unit || "题"}</div>`
    : `<div class="answer-result muted">本题暂无完整标准答案</div>`;
  revealAnswerPanel(resultHtml);
  els.revealBtn.textContent = "已显示";
  els.revealBtn.disabled = true;
}

function selectGroupOption(itemId, key) {
  if (state.answerVisible) return;

  state.groupAnswers = state.groupAnswers || {};
  state.groupAnswers[itemId] = key;
  state.answered = true;

  const q = state.questions[state.index];
  applyGroupSelectionStyles(q, state.groupAnswers);
  snapshotCurrentAttempt();

  if (allGroupItemsAnswered(q, state.groupAnswers)) {
    revealGroupAnswer();
  }
}

function applyGroupSelectionStyles(q, answers) {
  if (!isGroupSet(q)) return;
  for (const item of q.groupItems) {
    const row = els.card.querySelector(`.group-item[data-item="${CSS.escape(item.itemId)}"]`);
    if (!row) continue;
    row.querySelectorAll(".group-option").forEach((el) => {
      el.classList.toggle("selected", answers?.[item.itemId] === el.dataset.key);
    });
  }
}

function applyGroupAnswerStyles(q, answers) {
  if (!isGroupSet(q)) return;
  for (const item of q.groupItems) {
    const row = els.card.querySelector(`.group-item[data-item="${CSS.escape(item.itemId)}"]`);
    if (!row) continue;
    const correctKey = item.answer;
    row.querySelectorAll(".group-option").forEach((el) => {
      el.classList.add("disabled");
      const optionKey = el.dataset.key;
      const userKey = answers?.[item.itemId];
      if (userKey && optionKey === userKey) {
        el.classList.add(userKey === correctKey ? "correct" : "incorrect");
      } else if (correctKey && optionKey === correctKey) {
        el.classList.add("correct");
      }
    });
  }
}

function selectOption(key) {
  if (state.answered) return;

  const q = state.questions[state.index];
  if (!isChoiceQuestion(q)) return;

  state.selectedAnswer = key;
  state.answered = true;
  state.answerVisible = true;

  const correctKey = normalizeAnswer(q.answer);
  const isCorrect = correctKey && key === correctKey;

  els.card.querySelectorAll(".option").forEach((el) => {
    const optionKey = el.dataset.key;
    el.classList.add("disabled");
    if (optionKey === key) {
      el.classList.add(isCorrect ? "correct" : "incorrect");
    } else if (!isCorrect && optionKey === correctKey) {
      el.classList.add("correct");
    }
  });

  let resultHtml = "";
  if (!correctKey) {
    resultHtml = `<div class="answer-result muted">你选择了 ${key}，题库暂无标准答案，无法判定对错</div>`;
  } else if (isCorrect) {
    resultHtml = `<div class="answer-result correct">✓ 你选择了 ${key}，与题库参考答案一致</div>`;
  } else {
    resultHtml = `<div class="answer-result incorrect">✗ 你选择了 ${key}，题库参考答案是 ${correctKey}</div>`;
  }

  revealAnswerPanel(resultHtml);
  snapshotCurrentAttempt();
  els.revealBtn.disabled = true;
}

function renderGroupQuestion(q) {
  const config = getGroupConfig(q);
  const sourceClass = q.source === "bb" ? "bb" : q.source === "pay" ? "pay" : "";
  const passage = (q.stem || "").replace(config.stripPrefix, "");
  const pool = q.choicePool;
  const poolHtml =
    q.groupKind === "dialogue" && pool
      ? `
    <div class="passage-label">【选项池】</div>
    <div class="choice-pool">
      ${Object.keys(pool)
        .sort()
        .map((key) => `<span class="pool-option"><strong>${key}.</strong> ${escapeHtml(pool[key])}</span>`)
        .join("")}
    </div>`
      : "";

  const itemsHtml = q.groupItems
    .map((item) => {
      const options = item.options || {};
      const optionsHtml = Object.keys(options)
        .sort()
        .map(
          (key) => `
          <div class="option selectable group-option" data-item="${escapeHtml(item.itemId)}" data-key="${key}" role="button" tabindex="0">
            <span class="option-key">${key}</span>
            <span class="option-text">${escapeHtml(options[key])}</span>
          </div>`
        )
        .join("");
      const promptHtml =
        q.groupKind === "reading"
          ? `<div class="group-item-prompt">${escapeHtml(item.prompt)}</div>`
          : "";
      return `
        <section class="group-item" data-item="${escapeHtml(item.itemId)}">
          <div class="group-item-label">${escapeHtml(item.label)}</div>
          ${promptHtml}
          <div class="options group-options">${optionsHtml}</div>
        </section>`;
    })
    .join("");

  els.card.innerHTML = `
    <div class="meta">
      <span class="tag">${escapeHtml(q.subject)}</span>
      <span class="tag">${q.year} 年</span>
      <span class="tag">${escapeHtml(config.typeName)}</span>
      <span class="tag">第 ${escapeHtml(String(q.number))} 题 · ${q.groupItems.length} ${config.unit}</span>
      <span class="tag tag-type">${escapeHtml(config.typeName)}</span>
      <span class="tag tag-source ${sourceClass}">${escapeHtml(q.source_label || "未知来源")}</span>
    </div>
    <div class="passage-label">${escapeHtml(config.materialTag)}</div>
    <div class="stem group-passage">${escapeHtml(passage)}</div>
    ${poolHtml}
    <div class="passage-label">【作答】请逐${config.unit === "题" ? "题" : "空"}选择答案，全部选完后自动核对</div>
    <div class="group-items">${itemsHtml}</div>
    <div id="answerBox" class="answer-panel hidden"></div>
  `;
}

function renderQuestion() {
  const q = state.questions[state.index];
  if (!q) return;

  state.answerVisible = false;
  state.selectedAnswer = null;
  state.groupAnswers = {};
  state.answered = false;
  state.aiLoading = false;
  state.analyzeRequestId += 1;
  updateProgress();

  if (isGroupSet(q)) {
    const attempt = state.attempts[state.index];
    if (attempt) {
      state.groupAnswers = { ...(attempt.groupAnswers || {}) };
      state.answerVisible = attempt.viewedAnswer;
      state.answered = Boolean(
        attempt.viewedAnswer || Object.keys(state.groupAnswers).length
      );
    }

    els.revealBtn.textContent = state.answerVisible ? "已显示" : "显示答案";
    els.revealBtn.disabled = state.answerVisible;
    els.revealBtn.classList.remove("hidden");

    renderGroupQuestion(q);
    if (state.answerVisible) {
      restoreAttempt(state.index);
    } else {
      applyGroupSelectionStyles(q, state.groupAnswers);
    }

    els.prevBtn.disabled = state.index === 0;
    els.nextBtn.textContent = state.index === state.questions.length - 1 ? "查看汇总 ✓" : "下一题 →";
    return;
  }

  const choice = isChoiceQuestion(q);
  els.revealBtn.textContent = "显示答案";
  els.revealBtn.disabled = false;
  els.revealBtn.classList.toggle("hidden", choice);

  const options = parseOptions(q.options);
  const optionsHtml = options
    ? Object.keys(options)
        .sort()
        .map(
          (key) => `
          <div class="option${choice ? " selectable" : ""}" data-key="${key}"${choice ? ' role="button" tabindex="0"' : ""}>
            <span class="option-key">${key}</span>
            <span class="option-text">${escapeHtml(options[key])}</span>
          </div>`
        )
        .join("")
    : "";

  const sourceClass = q.source === "bb" ? "bb" : q.source === "pay" ? "pay" : "";
  els.card.innerHTML = `
    <div class="meta">
      <span class="tag">${escapeHtml(q.subject)}</span>
      <span class="tag">${q.year} 年</span>
      <span class="tag">第 ${q.number} 题</span>
      <span class="tag tag-type">${escapeHtml(questionDisplayType(q))}</span>
      <span class="tag tag-source ${sourceClass}">${escapeHtml(q.source_label || "未知来源")}</span>
    </div>
    <div class="stem">${escapeHtml(q.stem)}</div>
    ${optionsHtml ? `<div class="options">${optionsHtml}</div>` : ""}
    <div id="answerBox" class="answer-panel hidden"></div>
  `;

  els.prevBtn.disabled = state.index === 0;
  els.nextBtn.textContent = state.index === state.questions.length - 1 ? "查看汇总 ✓" : "下一题 →";
  restoreAttempt(state.index);
}

function showAnswer() {
  const q = state.questions[state.index];
  if (!q) return;

  if (isGroupSet(q)) {
    revealGroupAnswer();
    return;
  }

  state.answerVisible = true;
  revealAnswerPanel("");
  snapshotCurrentAttempt();
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
  const subjects = await api("api/subjects");
  subjects.forEach((name) => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    els.subject.appendChild(opt);
  });
  await refreshYears();
  refreshTypeOptions();
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
  const years = await api(`api/years${qs ? `?${qs}` : ""}`);
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
  const stats = await api(`api/stats${qs ? `?${qs}` : ""}`);
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
          const badgeClass = item.source === "bb" ? "bb" : item.source === "pay" ? "pay" : "web";
          const badgeText = item.source === "bb" ? "bb" : item.source === "pay" ? "pay" : "网";
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
  appendTypeFilter(params);
  if (els.source.value) params.set("source", els.source.value);

  try {
    const questions = groupMaterialQuestions(await api(`api/questions/random?${params}`));
    state.questions = questions;
    state.index = 0;
    state.attempts = [];
    state.sessionStartedAt = Date.now();
    els.results.classList.add("hidden");
    els.quizSummary.classList.add("hidden");
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
  appendTypeFilter(params);
  if (els.source.value) params.set("source", els.source.value);

  try {
    const items = await api(`api/questions/search?${params}`);
    renderResults(items);
    setMessage(`找到 ${items.length} 条结果`);
    els.results.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setMessage(err.message, true);
  }
}

async function onFilterChange() {
  refreshTypeOptions();
  await refreshYears();
  await loadStats();
}

els.card.addEventListener("click", (e) => {
  const option = e.target.closest(".option.selectable:not(.disabled)");
  if (!option?.dataset.key) return;
  if (option.dataset.item) {
    selectGroupOption(option.dataset.item, option.dataset.key);
    return;
  }
  selectOption(option.dataset.key);
});

els.card.addEventListener("keydown", (e) => {
  const option = e.target.closest(".option.selectable:not(.disabled)");
  if (!option?.dataset.key) return;
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    if (option.dataset.item) {
      selectGroupOption(option.dataset.item, option.dataset.key);
      return;
    }
    selectOption(option.dataset.key);
  }
});

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
    snapshotCurrentAttempt();
    state.index -= 1;
    renderQuestion();
  }
});
els.nextBtn.addEventListener("click", () => {
  if (state.index < state.questions.length - 1) {
    snapshotCurrentAttempt();
    state.index += 1;
    renderQuestion();
  } else {
    showQuizSummary();
  }
});
els.restartBtn?.addEventListener("click", () => {
  els.quizSummary?.classList.add("hidden");
  setMessage("可调整条件后重新开始练习。");
  window.scrollTo({ top: 0, behavior: "smooth" });
});

loadFilters()
  .then(async () => {
    await loadStats();
    const status = await api("api/ai/status");
    state.aiAvailable = Boolean(status.available);
  })
  .catch((err) => setMessage(err.message, true));
