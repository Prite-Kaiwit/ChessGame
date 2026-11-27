// หน้า /board: รับภาพและสถานะจากเซิร์ฟเวอร์ผ่าน WebSocket แล้วแสดงผล
// - ข้อความ binary: ไบต์แรกบอกชนิด 0x01 = ภาพกล้อง, 0x02 = ภาพกระดานที่ดัดตรงแล้ว ตามด้วย JPEG
// - ข้อความ text  : JSON ที่มี type = "state" (สถานะเกม) หรือ "dip" (สถานะ DIP)

const $ = (id) => document.getElementById(id);
const boardElement = $("chessboard");
const fallbackElement = $("fallback-board");
const connectionLabel = $("board-connection");
const frameElement = $("live-frame");
const framePlaceholder = $("live-placeholder");
const errorLabel = $("board-error");

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

let chessground = null;   // อ็อบเจกต์กระดาน Chessground (null = ใช้กระดานสำรอง)
let lastState = null;     // สถานะล่าสุด ใช้วาดลูกศรใหม่ตอนสลับธีม
let changedSquares = [];  // ช่องที่ภาพเปลี่ยน จากปุ่มเดินเสร็จครั้งล่าสุด (วาดเป็นวงกลม)
let boardSocket = null;
let reconnectTimer = null;
let leavingPage = false;

// ---------- นับ fps ของภาพที่หน้า board ได้รับ ----------
let framesThisSecond = 0;
const fpsTimer = window.setInterval(() => {
  $("camera-fps").textContent = framesThisSecond ? `${framesThisSecond} fps` : "รอภาพ";
  framesThisSecond = 0;
}, 1000);

// ---------- ลูกศรตาเดินแนะนำ ----------
// สีลูกศรอ่านจาก CSS variable --accent ของธีมปัจจุบัน
// ตั้งชื่อ brush แยกตามธีม เพื่อให้ Chessground วาดลูกศร (และหัวลูกศร) ใหม่เมื่อสลับธีม
function accentBrush() {
  const theme = document.documentElement.dataset.theme || "light";
  const color = getComputedStyle(document.documentElement).getPropertyValue("--accent").trim();
  const name = `accent-${theme}`;
  return { name, def: { key: name, color, opacity: 0.85, lineWidth: 12 } };
}

function isUci(move) {
  return typeof move === "string" && /^[a-h][1-8][a-h][1-8]/.test(move);
}

function drawSuggestion(uci) {
  if (!chessground) return;
  const brush = accentBrush();
  chessground.set({ drawable: { brushes: { [brush.name]: brush.def } } });
  const shapes = isUci(uci) ? [{ orig: uci.slice(0, 2), dest: uci.slice(2, 4), brush: brush.name }] : [];
  changedSquares.forEach((square) => shapes.push({ orig: square, brush: "red" }));
  chessground.setAutoShapes(shapes);
}

// แสดงลูกศรตาแนะนำเฉพาะตาของเรา (ตาฝั่งตรงข้ามรอกระดานจริง)
function suggestionFor(state) {
  return state && state.our_turn !== false ? state.best_move : null;
}

window.addEventListener("themechange", () => drawSuggestion(suggestionFor(lastState)));

// ---------- กระดานสำรอง (ใช้เมื่อโหลด Chessground ไม่ได้) ----------
const pieceSymbols = {
  P: "♙", N: "♘", B: "♗", R: "♖", Q: "♕", K: "♔",
  p: "♟", n: "♞", b: "♝", r: "♜", q: "♛", k: "♚",
};

function renderFallback(fen, bestMove) {
  // แปลงส่วนแรกของ FEN เป็นตาราง 8x8: แถวแรกของ FEN คือแถว 8 (บนสุด)
  const rows = fen.split(" ")[0].split("/");
  const grid = rows.map((row) => {
    const cells = [];
    for (const token of row) {
      if (/\d/.test(token)) cells.push(...Array(Number(token)).fill(null));
      else cells.push(token);
    }
    return cells;
  });
  const suggested = isUci(bestMove) ? [bestMove.slice(0, 2), bestMove.slice(2, 4)] : [];

  fallbackElement.replaceChildren();
  for (let rank = 0; rank < 8; rank += 1) {
    for (let file = 0; file < 8; file += 1) {
      const name = `${String.fromCharCode(97 + file)}${8 - rank}`;
      const square = document.createElement("div");
      // ช่อง a8 (rank 0, file 0) เป็นช่องสว่าง: ผลรวมคู่ = สว่าง, คี่ = เข้ม
      square.className = `fallback-square ${(rank + file) % 2 ? "dark" : "light"}`;
      if (suggested.includes(name)) square.classList.add("suggested");
      const piece = grid[rank]?.[file];
      if (piece) square.textContent = pieceSymbols[piece];
      fallbackElement.append(square);
    }
  }
  boardElement.hidden = true;
  fallbackElement.hidden = false;
}

// ---------- ประวัติตาเดิน: เลขตา | ขาว | ดำ ----------
function renderHistory(history) {
  const list = $("move-history");
  list.replaceChildren();
  if (!history.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "ยังไม่มีการเดิน";
    list.append(empty);
    return;
  }
  // จับคู่ทีละ 2 ply: (ขาว, ดำ) เป็นหนึ่งตาเต็ม
  for (let i = 0; i < history.length; i += 2) {
    const cells = [`${i / 2 + 1}.`, history[i]?.san ?? "", history[i + 1]?.san ?? ""];
    cells.forEach((text, index) => {
      const cell = document.createElement("li");
      if (index === 0) cell.className = "num";
      cell.textContent = text;
      list.append(cell);
    });
  }
  list.scrollTop = list.scrollHeight;
}

// ---------- แสดงสถานะเกม ----------
function showState(state) {
  if (!state || typeof state.fen !== "string") return;
  lastState = state;

  $("fen-value").textContent = state.fen;
  const turnName = state.turn === "black" ? "ดำ" : "ขาว";
  $("turn-indicator").textContent = state.our_turn === false ? `รอฝั่งตรงข้าม (${turnName})` : `ตาเรา (${turnName})`;
  $("turn-indicator").classList.toggle("is-ok", state.our_turn !== false);
  $("best-move").textContent = state.our_turn === false ? "รอฝั่งตรงข้ามเดิน" : state.best_move || "—";
  document.querySelectorAll('input[name="player-color"]').forEach((radio) => {
    radio.checked = radio.value === (state.player_color || "white");
  });
  if (typeof state.auto_detect === "boolean") $("auto-detect").checked = state.auto_detect;
  $("evaluation-value").textContent = formatEvaluation(state.evaluation);
  $("search-depth").textContent = state.depth ? `${state.depth} ตา` : "—";
  $("search-nodes").textContent =
    typeof state.nodes === "number"
      ? `${state.nodes.toLocaleString()} (${state.search_ms ?? 0} ms)`
      : "—";

  // แถบเตือนเดินผิดกฎ: แสดงเมื่อเซิร์ฟเวอร์ส่ง illegal_move มา (ใช้จริงเมื่อ ML อ่านกระดานได้)
  const warning = $("move-warning");
  warning.hidden = !state.illegal_move;
  if (state.illegal_move) warning.textContent = `ตรวจพบการเดินผิดกฎ: ${state.illegal_move}`;

  renderHistory(Array.isArray(state.history) ? state.history : []);

  if (chessground) {
    chessground.set({
      fen: state.fen,
      turnColor: state.turn,
      lastMove: isUci(state.last_move)
        ? [state.last_move.slice(0, 2), state.last_move.slice(2, 4)]
        : undefined,
      orientation: state.player_color === "black" ? "black" : "white", // ฝั่งเราอยู่ล่างเสมอ
      movable: { color: state.is_game_over ? undefined : state.turn, dests: legalDests(state.legal_moves) },
    });
    drawSuggestion(suggestionFor(state));
  } else {
    renderFallback(state.fen, state.best_move);
  }
}

// แปลงรายการ UCI เป็น Map ต้นทาง → [ปลายทาง] ตามที่ Chessground ต้องการ
function legalDests(moves) {
  const dests = new Map();
  (Array.isArray(moves) ? moves : []).forEach((uci) => {
    const from = uci.slice(0, 2);
    const to = uci.slice(2, 4);
    if (!dests.has(from)) dests.set(from, []);
    if (!dests.get(from).includes(to)) dests.get(from).push(to);
  });
  return dests;
}

// ผู้เล่นลากหมากบนจอ (แก้เมื่อระบบอ่านภาพไม่ได้) โปรโมตเป็นควีนอัตโนมัติ
async function onBoardMove(from, to) {
  let uci = from + to;
  if (lastState?.legal_moves?.includes(`${uci}q`)) uci += "q";
  changedSquares = [];
  const payload = await postAction("/api/game/move", { uci });
  if (payload) showMoveStatus(payload.notice || `เดิน ${uci} แล้ว`, Boolean(payload.notice));
  else if (lastState) showState(lastState); // เดินไม่สำเร็จ วางหมากกลับที่เดิม
}

// ---------- ผลของปุ่มเดินเสร็จ ----------
function showMoveStatus(text, warn = false) {
  const label = $("move-status");
  label.textContent = text;
  label.classList.toggle("is-warn", warn);
  label.hidden = !text;
}

// แสดงผลการหาตาเดินจากภาพ (มาจากปุ่มเดินเสร็จ หรือจากการตรวจจับอัตโนมัติผ่าน WebSocket)
function showDetection(result) {
  changedSquares = Array.isArray(result.changed) ? result.changed : [];
  const changed = changedSquares.length ? ` · ช่องที่เปลี่ยน: ${changedSquares.join(", ")}` : "";
  if (result.result === "moved") {
    changedSquares = [];
    const who = result.mover
      ? (result.mover === (lastState?.player_color || "white") ? "เรา" : "ฝั่งตรงข้าม")
      : "";
    showMoveStatus(`${who ? `${who}: ` : ""}${result.message}${changed} · ถ้าผิดกด Undo แล้วลากหมากเอง`);
  } else if (result.result === "baseline") {
    showMoveStatus(result.message);
  } else {
    const options = (result.candidates || []).map((c) => c.san).join(", ");
    showMoveStatus(
      `${result.message}${changed}${options ? ` · ตัวเลือก: ${options}` : ""} · ลากหมากบนกระดานเพื่อบอกตาเดิน`,
      true,
    );
  }
  drawSuggestion(suggestionFor(lastState));
}

async function moveDone() {
  const payload = await postAction("/api/game/move-done", undefined, false);
  if (!payload) return;
  showState(payload.state);
  showDetection(payload);
}

// ---------- แผง ML ----------
function showMl(status) {
  $("ml-model").textContent = status.model || "ยังไม่โหลด";
  const reading = status.reading;
  $("ml-confidence").textContent = reading ? `${(reading.mean_confidence * 100).toFixed(1)}%` : "—";
  $("ml-uncertain").textContent = reading ? (reading.uncertain.join(", ") || "ไม่มี") : "—";
  $("ml-mismatch").textContent = reading ? (reading.mismatches.join(", ") || "ไม่มี") : "—";
  const data = status.dataset || {};
  $("ml-collect").checked = Boolean(data.enabled);
  $("ml-capture").disabled = !data.enabled;
  const c = data.counts || {};
  $("ml-dataset").textContent = data.boards
    ? `เก็บแล้ว ${data.boards} ภาพ = ${data.samples} ช่อง (ว่าง ${c.empty} · ขาว ${c.white} · ดำ ${c.black})`
    : "ยังไม่มีข้อมูล";
}

async function mlAction(path, body) {
  errorLabel.textContent = "";
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    showMl(payload);
  } catch (error) {
    errorLabel.textContent = error instanceof Error ? error.message : "เรียก API ไม่สำเร็จ";
  }
}

// ---------- เลือกสี / โหมดอัตโนมัติ ----------
async function saveSettings(body) {
  const payload = await postAction("/api/game/settings", body);
  if (!payload && lastState) showState(lastState); // บันทึกไม่สำเร็จ คืนค่าเดิมบนจอ
}
document.querySelectorAll('input[name="player-color"]').forEach((radio) => {
  radio.addEventListener("change", () => saveSettings({ player_color: radio.value }));
});
$("auto-detect").addEventListener("change", (event) => saveSettings({ auto_detect: event.target.checked }));

$("ml-collect").addEventListener("change", (event) => mlAction("/api/ml/collect", { enabled: event.target.checked }));
$("ml-capture").addEventListener("click", () => mlAction("/api/ml/capture"));
$("ml-reload").addEventListener("click", () => mlAction("/api/ml/reload"));

// ---------- WebSocket ----------
function setConnection(text, status) {
  connectionLabel.textContent = text;
  connectionLabel.classList.toggle("is-ok", status === "ok");
  connectionLabel.classList.toggle("is-bad", status === "bad");
}

// แสดง JPEG ใน <img> ผ่าน object URL แล้วคืนหน่วยความจำเมื่อโหลดเสร็จ
function showImage(img, placeholder, jpegBytes) {
  const url = URL.createObjectURL(new Blob([jpegBytes], { type: "image/jpeg" }));
  img.onload = () => URL.revokeObjectURL(url);
  img.src = url;
  img.hidden = false;
  placeholder.hidden = true;
}

function handleBinary(buffer) {
  const kind = new Uint8Array(buffer, 0, 1)[0];
  const jpeg = buffer.slice(1);
  if (kind === 0x01) {
    showImage(frameElement, framePlaceholder, jpeg);
    framesThisSecond += 1;
  } else if (kind === 0x02) {
    showImage($("warped-frame"), $("warped-placeholder"), jpeg);
  }
}

// ---------- สถานะ DIP ----------
function showDip(status) {
  const pill = $("dip-status");
  pill.classList.remove("is-ok", "is-bad");
  if (!status.calibrated) {
    pill.textContent = "ยังไม่ calibrate";
    $("warped-frame").hidden = true;
    $("warped-placeholder").hidden = false;
    $("warped-placeholder").textContent = "กด Calibrate เพื่อเลือก 4 มุมกระดาน";
    return;
  }
  // D = ค่า frame difference ของเฟรมล่าสุด, นิ่ง = D < T ติดกัน N เฟรม
  const diff = typeof status.diff === "number" ? ` · D=${status.diff.toFixed(1)}` : "";
  const waiting = status.has_reference === false ? " · รอภาพก่อนเดิน" : "";
  pill.textContent = `${status.still ? "ภาพนิ่ง" : "กำลังขยับ"}${diff}${waiting}`;
  if (status.still) pill.classList.add("is-ok");
}

function connect() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  boardSocket = new WebSocket(`${protocol}//${location.host}/ws/board`);
  boardSocket.binaryType = "arraybuffer";
  boardSocket.addEventListener("open", () => setConnection("เชื่อมต่อแล้ว", "ok"));
  boardSocket.addEventListener("message", (event) => {
    if (typeof event.data !== "string") {
      handleBinary(event.data);
      return;
    }
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      errorLabel.textContent = "ได้รับสถานะจากเซิร์ฟเวอร์ในรูปแบบที่ไม่ถูกต้อง";
      return;
    }
    if (message.type === "dip") showDip(message);
    else if (message.type === "ml") showMl(message);
    else if (message.type === "detect") showDetection(message);
    else showState(message);
  });
  boardSocket.addEventListener("close", () => {
    setConnection("ขาดการเชื่อมต่อ", "bad");
    // ลองเชื่อมต่อใหม่อัตโนมัติทุก 1.5 วินาที
    if (!leavingPage) reconnectTimer = window.setTimeout(connect, 1500);
  });
}

// คะแนนหน่วยเบี้ย: ค่าเกิน ±900 คือ AI เห็นรุกจน (MATE_SCORE = 100000 centipawn)
function formatEvaluation(value) {
  if (typeof value !== "number") return "—";
  if (value >= 900) return "ขาวรุกจนได้";
  if (value <= -900) return "ดำรุกจนได้";
  return (value > 0 ? "+" : "") + value.toFixed(2);
}

// ---------- ปุ่มด้านล่าง ----------
const actionButtons = document.querySelectorAll(".action-bar button");

// คืน payload เมื่อสำเร็จ หรือ null เมื่อผิดพลาด (แสดงข้อความผิดพลาดให้แล้ว)
async function postAction(path, body = undefined, applyState = true) {
  errorLabel.textContent = "";
  // AI ใช้เวลาคิดสักครู่ ปิดปุ่มไว้กันกดซ้ำ
  actionButtons.forEach((button) => { button.disabled = true; });
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    if (applyState) showState(payload);
    return payload;
  } catch (error) {
    errorLabel.textContent = error instanceof Error ? error.message : "เรียก API ไม่สำเร็จ";
    return null;
  } finally {
    actionButtons.forEach((button) => { button.disabled = false; });
  }
}

function clearMoveStatus() {
  changedSquares = [];
  showMoveStatus("");
}

$("move-done").addEventListener("click", moveDone);
$("new-game").addEventListener("click", () => { clearMoveStatus(); postAction("/api/game/new"); });
$("undo-move").addEventListener("click", () => { clearMoveStatus(); postAction("/api/game/undo"); });

// Spacebar = เดินเสร็จ (เหมือนกดนาฬิกาหมากรุก) กดค้างไม่ซ้ำ และไม่ชนกับปุ่มที่โฟกัสอยู่
document.addEventListener("keydown", (event) => {
  if (event.code !== "Space" || event.repeat) return;
  if (event.target instanceof HTMLElement && event.target.closest("input, textarea, select")) return;
  event.preventDefault();
  if (!$("move-done").disabled) moveDone();
});
$("random-move").addEventListener("click", () => postAction("/api/test/random-move"));
$("ai-move").addEventListener("click", () => postAction("/api/game/ai-move"));

// ---------- เริ่มต้น ----------
try {
  // โหลด Chessground จากสำเนาในเครื่อง (web/static/vendor/) ใช้ได้แม้ไม่มีอินเทอร์เน็ต
  const module = await import("/static/vendor/chessground.min.js");
  chessground = module.Chessground(boardElement, {
    fen: START_FEN,
    coordinates: true,
    drawable: { enabled: false, visible: true },
    movable: { free: false, showDests: true, events: { after: onBoardMove } },
    premovable: { enabled: false },
  });
} catch {
  renderFallback(START_FEN, null);
  errorLabel.textContent = "โหลด Chessground ไม่สำเร็จ กำลังใช้กระดานสำรอง";
}
connect();

window.addEventListener("beforeunload", () => {
  leavingPage = true;
  window.clearInterval(fpsTimer);
  if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
  if (boardSocket) boardSocket.close();
});
