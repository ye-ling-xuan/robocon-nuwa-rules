import * as pdfjsLib from "/static/pdfjs/pdf.mjs";
import {quoteRanges, topLeftRectToViewport} from "/static/pdf-helpers.mjs";

pdfjsLib.GlobalWorkerOptions.workerSrc = "/static/pdfjs/pdf.worker.mjs";
const $ = (id) => document.getElementById(id);
const session = new URL(location.href).searchParams.get("session") || "";
const withSession = (path) => `${path}${path.includes("?") ? "&" : "?"}session=${encodeURIComponent(session)}`;
let pdf, pageNumber = 1, scale = 1, fitMode = true, selection = null;
let renderGeneration = 0, renderTask, textLayerTask, totalPages = 33;
let turns = new Map(), sampling = false, busy = false, demo = false, toastTimer;
let currentPage, currentViewport, currentStage, eventSource;

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $("toast").hidden = true; }, 6000);
}

async function api(path, body) {
  const response = await fetch(withSession(path), body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请求未完成，请重试。");
  return data;
}

function connection(connected, message) {
  $("connection").className = `connection ${connected ? "connected" : "error"}`;
  $("connection-text").textContent = message;
}

function updateCapabilities(data) {
  if (data.sampling_supported !== undefined) sampling = data.sampling_supported;
  if (data.sampling_busy !== undefined) busy = data.sampling_busy;
  $("question-input").disabled = !sampling || busy;
  $("send-button").disabled = !sampling || busy;
  $("question-input").placeholder = sampling ? (busy ? "Agent 正在回答…" : "问一个与规则有关的问题…") : "请在 Agent 聊天框提问…";
  $("input-mode").textContent = sampling ? "使用你的 Agent 回答" : "在 Agent 中继续";
  $("input-hint").textContent = sampling ? "回答由你的 Agent 提供。Enter 发送，Shift + Enter 换行。" : "请在 Agent 聊天框提问，回答会自动同步到这里。";
}

function buttonForCitation(citation, inline = false) {
  const button = document.createElement("button");
  button.className = inline ? "inline-citation" : "citation-badge";
  button.textContent = `${citation.clause_id} · P${citation.page}`;
  button.dataset.clauseId = citation.clause_id;
  button.title = citation.quote;
  button.type = "button";
  button.addEventListener("click", () => api("/api/jump", {clause_id: citation.clause_id}).catch(e => toast(e.message)));
  return button;
}

function appendPlainMarkdown(container, text) {
  // A small safe subset; model output never becomes HTML.
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  for (const token of tokens) {
    if (token.startsWith("**") && token.endsWith("**")) {
      const strong = document.createElement("strong"); strong.textContent = token.slice(2, -2); container.append(strong);
    } else if (token.startsWith("`") && token.endsWith("`")) {
      const code = document.createElement("code"); code.textContent = token.slice(1, -1); container.append(code);
    } else container.append(document.createTextNode(token));
  }
}

function answerBody(text, citations) {
  const body = document.createElement("div"); body.className = "answer-body";
  const pattern = /\[(\d+(?:\.\d+){0,2})\s*[·•|]\s*P\s*(\d+)\]/g;
  let offset = 0;
  for (const match of text.matchAll(pattern)) {
    appendPlainMarkdown(body, text.slice(offset, match.index));
    const citation = citations.find(c => c.clause_id === match[1] && c.page === Number(match[2]));
    if (citation) body.append(buttonForCitation(citation, true));
    else body.append(document.createTextNode(match[0]));
    offset = match.index + match[0].length;
  }
  appendPlainMarkdown(body, text.slice(offset));
  return body;
}

function renderTurn(turn) {
  const old = document.getElementById(`turn-${turn.id}`);
  const card = document.createElement("article"); card.className = "turn"; card.id = `turn-${turn.id}`;
  const meta = document.createElement("div"); meta.className = "question-meta";
  const label = document.createElement("span"); label.textContent = "你的提问";
  const time = document.createElement("time"); time.dateTime = turn.created_at;
  time.textContent = new Date(turn.created_at).toLocaleTimeString("zh-CN", {hour: "2-digit", minute: "2-digit", hour12: false});
  meta.append(label, time); card.append(meta);
  const question = document.createElement("h3"); question.className = "question-text"; question.textContent = turn.question; card.append(question);
  const answer = document.createElement("div"); answer.className = "answer-content";
  if (turn.answer) {
    const heading = document.createElement("div"); heading.className = "answer-heading";
    const mark = document.createElement("span"); mark.className = "mini-mark";
    heading.append(mark, document.createTextNode(demo ? "示例 · 规则解答" : "AGENT · 规则解答")); answer.append(heading, answerBody(turn.answer, turn.citations));
  } else {
    const pending = document.createElement("div"); pending.className = "pending";
    const dots = document.createElement("span"); dots.className = "pending-dots";
    for (let i = 0; i < 3; i++) dots.append(document.createElement("i"));
    pending.append(dots, document.createTextNode(turn.citations.length ? "已找到原文，等待 Agent 回答…" : "正在核对规则依据…")); answer.append(pending);
  }
  if (turn.citations.length) {
    const badges = document.createElement("div"); badges.className = "citation-list";
    for (const citation of turn.citations) badges.append(buttonForCitation(citation));
    answer.append(badges);
    const caption = document.createElement("p"); caption.className = "citations-caption"; caption.textContent = "点击引用，在右侧查看对应原文"; answer.append(caption);
  }
  card.append(answer);
  if (old) old.replaceWith(card); else $("turns").append(card);
}

function upsertTurn(turn) {
  const container = $("conversation");
  const nearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
  const isNew = !turns.has(turn.id);
  turns.set(turn.id, turn); $("empty-state").hidden = turns.size > 0;
  renderTurn(turn); markActive();
  if (nearBottom || isNew) container.scrollTop = container.scrollHeight;
}

function markActive() {
  document.querySelectorAll("[data-clause-id]").forEach(button => {
    const active = button.dataset.clauseId === selection?.clause_id;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("source-bar").classList.toggle("active", Boolean(selection));
  $("source-label").textContent = selection ? `当前依据 · ${selection.clause_id} · P${selection.page}` : "浏览规则原文";
  $("source-excerpt").textContent = selection ? selection.quote.replace(/\s+/g, " ") : "点击答案中的引用，自动翻页并高亮";
  $("source-excerpt").title = selection?.quote || "";
  $("cross-page-note").hidden = !selection?.cross_page;
  $("clear-highlight").hidden = !selection;
}

function segmentForPage() {
  if (!selection) return null;
  if (selection.page === pageNumber) return selection;
  return selection.segments?.find(s => s.page === pageNumber) || null;
}

function drawHighlights() {
  $("document-status").textContent = `PDF 物理页码 ${pageNumber} / ${totalPages}${segmentForPage() ? " · 原文已高亮" : ""}`;
  if (!currentStage) return;
  const layer = currentStage.querySelector(".highlights"); layer.replaceChildren();
  const target = segmentForPage();
  if (!target) return;
  const rects = target.rects?.length ? target.rects : target.bbox ? [target.bbox] : null;
  let boxes = [];
  if (rects) {
    boxes = rects.map(rect => topLeftRectToViewport(rect, currentPage.view, currentViewport));
  } else {
    const stageRect = currentStage.getBoundingClientRect();
    for (const range of quoteRanges(currentStage.querySelector(".textLayer"), target.quote)) {
      for (const rect of range.getClientRects()) boxes.push([rect.left - stageRect.left, rect.top - stageRect.top, rect.right - stageRect.left, rect.bottom - stageRect.top]);
    }
  }
  for (const [left, top, right, bottom] of boxes) {
    const rect = document.createElement("div"); rect.className = "highlight-rect";
    Object.assign(rect.style, {left: `${left}px`, top: `${top}px`, width: `${right-left}px`, height: `${bottom-top}px`});
    layer.append(rect);
  }
  if (!boxes.length) toast("此处未匹配到高亮，请结合本页原文核对引用。");
}

function scrollToHighlight() {
  const first = currentStage?.querySelector(".highlight-rect");
  const viewer = $("pdf-viewer");
  if (first) {
    const offset = first.getBoundingClientRect().top - viewer.getBoundingClientRect().top + viewer.scrollTop;
    viewer.scrollTo({top: Math.max(0, offset - viewer.clientHeight * .38), behavior: "instant"});
  } else viewer.scrollTop = 0;
}

async function renderPage(jumpToHighlight = true) {
  if (!pdf) return;
  const generation = ++renderGeneration;
  renderTask?.cancel(); textLayerTask?.cancel();
  try {
    const page = await pdf.getPage(pageNumber);
    if (generation !== renderGeneration) return;
    const base = page.getViewport({scale: 1});
    if (fitMode) scale = Math.max(.3, Math.min(3, ($( "pdf-viewer").clientWidth - (innerWidth <= 760 ? 32 : 56)) / base.width));
    const viewport = page.getViewport({scale});
    const stage = document.createElement("div"); stage.className = "pdf-page"; stage.dataset.page = String(pageNumber);
    stage.style.width = `${viewport.width}px`; stage.style.height = `${viewport.height}px`;
    stage.style.setProperty("--total-scale-factor", scale);
    const canvas = document.createElement("canvas"); const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(viewport.width * dpr); canvas.height = Math.round(viewport.height * dpr);
    canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`;
    canvas.setAttribute("aria-label", `规则原文第 ${pageNumber} 页`);
    const textLayer = document.createElement("div"); textLayer.className = "textLayer";
    const highlights = document.createElement("div"); highlights.className = "highlights"; highlights.setAttribute("aria-hidden", "true");
    stage.append(canvas, textLayer, highlights);
    renderTask = page.render({canvasContext: canvas.getContext("2d"), viewport, transform: dpr === 1 ? null : [dpr, 0, 0, dpr, 0, 0]});
    await renderTask.promise;
    if (generation !== renderGeneration) return;
    textLayerTask = new pdfjsLib.TextLayer({textContentSource: await page.getTextContent(), container: textLayer, viewport});
    await textLayerTask.render();
    if (generation !== renderGeneration) return;
    $("pdf-pages").replaceChildren(stage); $("viewer-message").hidden = true;
    currentPage = page; currentViewport = viewport; currentStage = stage;
    $("page-input").value = pageNumber; $("zoom-label").textContent = `${Math.round(scale * 100)}%`;
    $("prev-page").disabled = pageNumber <= 1; $("next-page").disabled = pageNumber >= totalPages;
    $("document-status").textContent = `PDF 物理页码 ${pageNumber} / ${totalPages}${segmentForPage() ? " · 原文已高亮" : ""}`;
    drawHighlights();
    if (jumpToHighlight) scrollToHighlight();
  } catch (error) {
    if (generation !== renderGeneration || error.name === "RenderingCancelledException" || error.name === "AbortException") return;
    $("viewer-message").hidden = false; $("viewer-message").replaceChildren();
    const message = document.createElement("p"); message.textContent = "原文载入失败，请检查 Agent 是否仍在运行，然后刷新页面。"; $("viewer-message").append(message);
    console.error("Local PDF rendering failed", error.name);
  }
}

function selectCitation(citation) {
  selection = citation; markActive();
  if (citation) {
    pageNumber = citation.page;
    renderPage();
  } else drawHighlights();
}

function applySnapshot(snapshot) {
  demo = Boolean(snapshot.demo);
  document.querySelector(".panel-heading .subtle-tag").textContent = demo ? "示例会话" : "与 Agent 同步";
  turns = new Map(); $("turns").replaceChildren();
  for (const turn of snapshot.turns) upsertTurn(turn);
  $("empty-state").hidden = turns.size > 0;
  updateCapabilities(snapshot);
  selectCitation(snapshot.selected);
  if (demo) $("conversation").scrollTop = 0;
}

function connectEvents() {
  eventSource = new EventSource(withSession("/events"));
  eventSource.onopen = () => connection(true, demo ? "本地示例已连接" : "已连接 Agent 会话");
  eventSource.onerror = () => connection(false, "连接中，正在自动恢复");
  eventSource.addEventListener("snapshot", e => applySnapshot(JSON.parse(e.data)));
  for (const name of ["question", "answer"]) eventSource.addEventListener(name, e => upsertTurn(JSON.parse(e.data).turn));
  eventSource.addEventListener("citations", e => {
    const data = JSON.parse(e.data), turn = turns.get(data.turn_id);
    if (turn) upsertTurn({...turn, citations: data.citations});
  });
  eventSource.addEventListener("jump", e => selectCitation(JSON.parse(e.data).citation));
  eventSource.addEventListener("clear", () => selectCitation(null));
  eventSource.addEventListener("capabilities", e => updateCapabilities(JSON.parse(e.data)));
  eventSource.addEventListener("notice", e => toast(JSON.parse(e.data).message));
}

function setPage(number) {
  const parsed = Number(number);
  pageNumber = Number.isFinite(parsed) ? Math.max(1, Math.min(totalPages, Math.trunc(parsed))) : pageNumber;
  renderPage();
}
$("prev-page").addEventListener("click", () => setPage(pageNumber - 1));
$("next-page").addEventListener("click", () => setPage(pageNumber + 1));
$("page-input").addEventListener("change", e => setPage(e.target.value));
$("page-input").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); setPage(e.target.value); } });
$("zoom-in").addEventListener("click", () => { fitMode = false; scale = Math.min(3, scale + .15); renderPage(); });
$("zoom-out").addEventListener("click", () => { fitMode = false; scale = Math.max(.3, scale - .15); renderPage(); });
$("fit-width").addEventListener("click", () => { fitMode = true; renderPage(); });
$("clear-highlight").addEventListener("click", () => api("/api/clear", {}).catch(e => toast(e.message)));
$("question-form").addEventListener("submit", async e => {
  e.preventDefault();
  const question = $("question-input").value.trim();
  if (!sampling || busy || !question) return;
  $("question-input").value = ""; updateCapabilities({sampling_busy: true});
  try { await api("/api/ask", {question}); } catch (error) { toast(error.message); }
  finally { updateCapabilities({sampling_busy: false}); }
});
$("question-input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("question-form").requestSubmit(); }
});
document.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", async () => {
  if (sampling) { $("question-input").value = button.dataset.question; $("question-input").focus(); }
  else {
    try { await navigator.clipboard.writeText(button.dataset.question); toast("问题已复制，请粘贴到 Agent 聊天框。"); }
    catch { toast(`请在 Agent 里提问：${button.dataset.question}`); }
  }
}));

let resizeTimer;
function scheduleResize() { if (fitMode) { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => renderPage(), 160); } }
new ResizeObserver(scheduleResize).observe($("pdf-viewer"));
const splitter = $("splitter");
splitter.addEventListener("pointerdown", e => {
  splitter.setPointerCapture(e.pointerId); document.body.classList.add("resizing");
});
splitter.addEventListener("pointermove", e => {
  if (!splitter.hasPointerCapture(e.pointerId)) return;
  const workspace = $("workspace").getBoundingClientRect();
  if (innerWidth <= 760) {
    const height = Math.max(190, Math.min(workspace.height * .65, e.clientY - workspace.top));
    $("workspace").style.setProperty("--chat-height", `${height}px`);
  } else {
    const width = Math.max(280, Math.min(workspace.width * .6, e.clientX - workspace.left));
    document.documentElement.style.setProperty("--chat-width", `${width}px`);
    splitter.setAttribute("aria-valuenow", String(Math.round(width / workspace.width * 100)));
  }
});
for (const event of ["pointerup", "pointercancel", "lostpointercapture"]) splitter.addEventListener(event, e => {
  if (splitter.hasPointerCapture(e.pointerId)) splitter.releasePointerCapture(e.pointerId);
  document.body.classList.remove("resizing");
});
splitter.addEventListener("keydown", e => {
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
  e.preventDefault(); const mobile = innerWidth <= 760; const rect = $("workspace").getBoundingClientRect();
  const delta = ["ArrowLeft", "ArrowUp"].includes(e.key) ? -24 : 24;
  if (mobile) $("workspace").style.setProperty("--chat-height", `${Math.max(190, Math.min(rect.height * .65, $("splitter").getBoundingClientRect().top - rect.top + delta))}px`);
  else document.documentElement.style.setProperty("--chat-width", `${Math.max(280, Math.min(rect.width * .6, $("splitter").getBoundingClientRect().left - rect.left + delta))}px`);
});
const mobileQuery = matchMedia("(max-width:760px)");
function updateOrientation() { splitter.setAttribute("aria-orientation", mobileQuery.matches ? "horizontal" : "vertical"); }
mobileQuery.addEventListener("change", updateOrientation); updateOrientation();
window.addEventListener("beforeunload", () => eventSource?.close());

async function init() {
  try {
    const data = await api("/api/state");
    totalPages = data.rule_meta.page_count;
    $("page-total").textContent = totalPages; $("page-input").max = totalPages;
    $("dataset-label").textContent = `${data.rule_meta.version} · ${data.clause_count} 条原文索引 · ${totalPages} 页`;
    $("download-pdf").href = data.pdf_url;
    applySnapshot(data); connectEvents();
    pdf = await pdfjsLib.getDocument({url: data.pdf_url, cMapUrl: "/static/pdfjs/cmaps/", cMapPacked: true,
      standardFontDataUrl: "/static/pdfjs/standard_fonts/", wasmUrl: "/static/pdfjs/wasm/", isEvalSupported: false}).promise;
    await renderPage();
  } catch (error) {
    connection(false, "会话未连接");
    $("viewer-message").replaceChildren(document.createTextNode(error.message));
    toast("请使用 Agent 返回的完整链接，并保持 Agent 的 MCP 服务运行。");
  }
}
init();
