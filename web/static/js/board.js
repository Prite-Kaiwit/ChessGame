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
  chessground.setAutoShapes(
    isUci(uci) ? [{ orig: uci.slice(0, 2), dest: uci.slice(2, 4), brush: brush.name }] : []
  );
}

window.addEventListener("themechange", () => drawSuggestion(lastState?.best_move));

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
  $("turn-indicator").textContent = state.turn === "black" ? "ดำเดิน" : "ขาวเดิน";
  $("best-move").textContent = state.best_move || "—";
  $("evaluation-value").textContent =
    typeof state.evaluation === "number" ? state.evaluation.toFixed(2) : "—";
  $("search-depth").textContent = state.depth ?? "—";

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
    });
    drawSuggestion(state.best_move);
  } else {
    renderFallback(state.fen, state.best_move);
  }
}

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
  pill.textContent = `${status.still ? "ภาพนิ่ง" : "กำลังขยับ"}${diff}`;
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
    else showState(message);
  });
  boardSocket.addEventListener("close", () => {
    setConnection("ขาดการเชื่อมต่อ", "bad");
    // ลองเชื่อมต่อใหม่อัตโนมัติทุก 1.5 วินาที
    if (!leavingPage) reconnectTimer = window.setTimeout(connect, 1500);
  });
}

// ---------- ปุ่มด้านล่าง ----------
async function postAction(path) {
  errorLabel.textContent = "";
  try {
    const response = await fetch(path, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    showState(payload);
  } catch (error) {
    errorLabel.textContent = error instanceof Error ? error.message : "เรียก API ไม่สำเร็จ";
  }
}

$("new-game").addEventListener("click", () => postAction("/api/game/new"));
$("undo-move").addEventListener("click", () => postAction("/api/game/undo"));
$("random-move").addEventListener("click", () => postAction("/api/test/random-move"));

// ---------- เริ่มต้น ----------
try {
  // โหลด Chessground จากสำเนาในเครื่อง (web/static/vendor/) ใช้ได้แม้ไม่มีอินเทอร์เน็ต
  const module = await import("/static/vendor/chessground.min.js");
  chessground = module.Chessground(boardElement, {
    fen: START_FEN,
    coordinates: true,
    viewOnly: true,
    drawable: { enabled: false, visible: true },
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
