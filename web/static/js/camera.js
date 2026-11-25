// หน้า /camera (มือถือ): เปิดกล้องหลัง → ย่อภาพกว้าง 640px → เข้ารหัส JPEG → ส่งผ่าน WebSocket
//
// การคุม fps และกันภาพหน่วงสะสม (backpressure):
//   ทุก 1/fps วินาทีจะ "พยายาม" ส่งหนึ่งเฟรม แต่จะข้ามเฟรมนั้นถ้า
//     (1) เฟรมก่อนหน้ายังเข้ารหัส JPEG ไม่เสร็จ หรือ
//     (2) socket.bufferedAmount > 0 คือข้อมูลเฟรมก่อนยังค้างอยู่ในเครื่อง ส่งออกเน็ตไม่ทัน
//   ถ้าไม่ข้าม เฟรมจะกองรอในบัฟเฟอร์ แล้วภาพที่คอมเห็นจะช้ากว่าความจริงขึ้นเรื่อยๆ
(() => {
  const $ = (id) => document.getElementById(id);
  const video = $("camera-video");
  const startButton = $("start-camera");
  const stopButton = $("stop-camera");
  const status = $("connection-status");
  const fpsLabel = $("fps-value");
  const skippedLabel = $("skipped-value");
  const placeholder = $("video-placeholder");
  const errorLabel = $("camera-error");
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: false });

  const FRAME_WIDTH = 640;     // ความกว้างภาพที่ส่ง (พิกเซล)
  const JPEG_QUALITY = 0.7;    // คุณภาพ JPEG 0–1
  const FPS_KEY = "chessgame-camera-fps";

  let targetFps = readSavedFps();
  let stream = null;
  let socket = null;
  let sendTimer = null;
  let statsTimer = null;
  let encoding = false;        // กำลังเข้ารหัส JPEG อยู่หรือไม่
  let sentFrames = 0;
  let skippedFrames = 0;

  function readSavedFps() {
    try {
      const value = Number(localStorage.getItem(FPS_KEY));
      return [5, 10, 15, 20, 30].includes(value) ? value : 15;
    } catch {
      return 15;
    }
  }

  function setStatus(text, connected = false) {
    status.textContent = text;
    status.classList.toggle("is-ok", connected);
  }

  // ---------- ตัวเลือก fps ----------
  document.querySelectorAll('input[name="fps"]').forEach((radio) => {
    radio.checked = Number(radio.value) === targetFps;
    radio.addEventListener("change", () => {
      targetFps = Number(radio.value);
      try { localStorage.setItem(FPS_KEY, String(targetFps)); } catch { /* ไม่จำค่าก็ได้ */ }
      if (sendTimer !== null) startSending(); // เปลี่ยนได้ทันทีระหว่างส่ง
    });
  });

  function startSending() {
    if (sendTimer !== null) window.clearInterval(sendTimer);
    sendTimer = window.setInterval(sendFrame, 1000 / targetFps);
  }

  function stop() {
    if (sendTimer !== null) window.clearInterval(sendTimer);
    if (statsTimer !== null) window.clearInterval(statsTimer);
    sendTimer = null;
    statsTimer = null;
    if (socket) {
      socket.close();
      socket = null;
    }
    if (stream) {
      stream.getTracks().forEach((track) => track.stop());
      stream = null;
    }
    video.srcObject = null;
    placeholder.hidden = false;
    startButton.disabled = false;
    stopButton.disabled = true;
    fpsLabel.textContent = "0";
    skippedLabel.textContent = "0";
    setStatus("หยุดส่งภาพ");
  }

  async function start() {
    errorLabel.textContent = "";
    startButton.disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        // ขอกล้องหลัง และขอ 30 fps เพื่อให้มีเฟรมใหม่พอสำหรับทุกค่า fps ที่เลือก
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, frameRate: { ideal: 30 } },
      });
      video.srcObject = stream;
      await video.play();
      placeholder.hidden = true;

      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${protocol}//${location.host}/ws/camera`);
      socket.binaryType = "arraybuffer";
      socket.addEventListener("open", () => {
        setStatus("เชื่อมต่อแล้ว", true);
        stopButton.disabled = false;
        startSending();
        // อัปเดตสถิติทุก 1 วินาที: fps ที่ส่งได้จริง และจำนวนเฟรมที่ข้ามเพราะเน็ตไม่ทัน
        statsTimer = window.setInterval(() => {
          fpsLabel.textContent = String(sentFrames);
          skippedLabel.textContent = String(skippedFrames);
          sentFrames = 0;
          skippedFrames = 0;
        }, 1000);
      }, { once: true });
      socket.addEventListener("error", () => {
        errorLabel.textContent = "เชื่อมต่อ WebSocket ไม่สำเร็จ ตรวจสอบว่าเซิร์ฟเวอร์ยังทำงานอยู่";
        setStatus("เชื่อมต่อล้มเหลว");
      });
      socket.addEventListener("close", () => {
        if (stream) stop();
      }, { once: true });
    } catch (error) {
      stop();
      errorLabel.textContent = error instanceof Error ? error.message : "เปิดกล้องไม่สำเร็จ";
    }
  }

  function sendFrame() {
    if (!stream || !socket || socket.readyState !== WebSocket.OPEN || !video.videoWidth) return;
    // backpressure: เฟรมก่อนยังไม่เสร็จหรือยังค้างในบัฟเฟอร์ → ข้ามเฟรมนี้
    if (encoding || socket.bufferedAmount > 0) {
      skippedFrames += 1;
      return;
    }
    encoding = true;
    const scale = Math.min(1, FRAME_WIDTH / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(async (blob) => {
      try {
        if (blob && socket && socket.readyState === WebSocket.OPEN) {
          socket.send(await blob.arrayBuffer());
          sentFrames += 1;
        }
      } finally {
        encoding = false;
      }
    }, "image/jpeg", JPEG_QUALITY);
  }

  startButton.addEventListener("click", start);
  stopButton.addEventListener("click", stop);
})();
