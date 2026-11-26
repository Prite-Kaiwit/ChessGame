// หน้า /camera (มือถือ): เปิดกล้องหลัง → ย่อภาพกว้าง 640px → เข้ารหัส JPEG → ส่งผ่าน WebSocket
//
// การคุม fps และกันภาพหน่วงสะสม (backpressure):
//   ทุก 1/fps วินาทีจะ "พยายาม" ส่งหนึ่งเฟรม แต่จะข้ามเฟรมนั้นถ้า
//     (1) เฟรมก่อนหน้ายังเข้ารหัส JPEG ไม่เสร็จ หรือ
//     (2) socket.bufferedAmount > 0 คือข้อมูลเฟรมก่อนยังค้างอยู่ในเครื่อง ส่งออกเน็ตไม่ทัน
//   ถ้าไม่ข้าม เฟรมจะกองรอในบัฟเฟอร์ แล้วภาพที่คอมเห็นจะช้ากว่าความจริงขึ้นเรื่อยๆ
//
// การปรับเลนส์/ซูม:
//   - เลนส์: เลือกกล้องหลังแต่ละตัว (เช่น Ultra Wide / Wide / Telephoto บน iPhone) ผ่าน deviceId
//   - ซูม: ถ้าเบราว์เซอร์รองรับ zoom ของกล้องจริง (hardware) จะใช้ applyConstraints
//          ถ้าไม่รองรับจะใช้ "ซูมดิจิทัล" = ครอปกลางภาพก่อนย่อ แล้วส่งภาพที่ครอปแล้วไปเซิร์ฟเวอร์
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
  const lensSelect = $("lens-select");
  const zoomRange = $("zoom-range");
  const zoomValue = $("zoom-value");
  const zoomMode = $("zoom-mode");
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: false });

  const FRAME_WIDTH = 640;     // ความกว้างภาพที่ส่ง (พิกเซล)
  const JPEG_QUALITY = 0.7;    // คุณภาพ JPEG 0–1
  const FPS_KEY = "chessgame-camera-fps";
  const LENS_KEY = "chessgame-camera-lens";
  const DIGITAL_ZOOM_MAX = 3;  // ซูมดิจิทัลสูงสุด (เท่า)

  let targetFps = readSavedFps();
  let stream = null;
  let socket = null;
  let sendTimer = null;
  let statsTimer = null;
  let encoding = false;        // กำลังเข้ารหัส JPEG อยู่หรือไม่
  let sentFrames = 0;
  let skippedFrames = 0;
  let hardwareZoom = false;    // กล้องรองรับซูมจริงหรือไม่
  let digitalZoom = 1;         // ใช้เมื่อไม่มีซูมจริง

  function readSavedFps() {
    try {
      const value = Number(localStorage.getItem(FPS_KEY));
      return [5, 10, 15, 20, 30].includes(value) ? value : 15;
    } catch {
      return 15;
    }
  }

  function readSavedLens() {
    try { return localStorage.getItem(LENS_KEY) || ""; } catch { return ""; }
  }

  // เปิดกล้อง: deviceId ว่าง = ให้เบราว์เซอร์เลือกกล้องหลังเอง
  async function openCamera(deviceId) {
    const videoConstraints = {
      width: { ideal: 1280 },
      frameRate: { ideal: 30 }, // ขอ 30 fps เพื่อให้มีเฟรมใหม่พอสำหรับทุกค่า fps ที่เลือก
    };
    if (deviceId) videoConstraints.deviceId = { exact: deviceId };
    else videoConstraints.facingMode = { ideal: "environment" };

    let newStream;
    try {
      newStream = await navigator.mediaDevices.getUserMedia({ audio: false, video: videoConstraints });
    } catch (error) {
      if (!deviceId) throw error;
      // เลนส์ที่จำไว้อาจไม่มีแล้ว → กลับไปใช้กล้องหลังปกติ
      newStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { ...videoConstraints, deviceId: undefined, facingMode: { ideal: "environment" } },
      });
    }
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = newStream;
    video.srcObject = stream;
    await video.play();
    placeholder.hidden = true;
    setupZoom();
  }

  // รายชื่อกล้องหลัง (ชื่อจะอ่านได้หลังผู้ใช้อนุญาตกล้องแล้วเท่านั้น)
  async function listLenses() {
    const devices = await navigator.mediaDevices.enumerateDevices();
    const cams = devices.filter((d) => d.kind === "videoinput");
    const back = cams.filter((d) => !/front|หน้า|user|facetime/i.test(d.label));
    const list = back.length ? back : cams;
    const current = stream.getVideoTracks()[0].getSettings().deviceId || "";

    lensSelect.replaceChildren();
    list.forEach((d, i) => {
      const option = document.createElement("option");
      option.value = d.deviceId;
      option.textContent = d.label || `กล้อง ${i + 1}`;
      option.selected = d.deviceId === current;
      lensSelect.append(option);
    });
    lensSelect.disabled = list.length < 2;
  }

  lensSelect.addEventListener("change", async () => {
    const id = lensSelect.value;
    try { localStorage.setItem(LENS_KEY, id); } catch { /* ไม่จำค่าก็ได้ */ }
    lensSelect.disabled = true;
    try {
      await openCamera(id); // WebSocket ยังเปิดอยู่ ส่งต่อได้ทันที
    } catch (error) {
      errorLabel.textContent = error instanceof Error ? error.message : "สลับเลนส์ไม่สำเร็จ";
    } finally {
      lensSelect.disabled = lensSelect.options.length < 2;
    }
  });

  // ---------- ซูม ----------
  function setupZoom() {
    const track = stream.getVideoTracks()[0];
    const caps = typeof track.getCapabilities === "function" ? track.getCapabilities() : {};
    hardwareZoom = Boolean(caps.zoom && caps.zoom.max > caps.zoom.min);
    digitalZoom = 1;
    video.style.transform = "";
    if (hardwareZoom) {
      zoomRange.min = String(caps.zoom.min);
      zoomRange.max = String(Math.min(caps.zoom.max, 10));
      zoomRange.step = String(caps.zoom.step || 0.1);
      zoomRange.value = String(track.getSettings().zoom || caps.zoom.min);
      zoomMode.textContent = "(ซูมกล้องจริง)";
    } else {
      zoomRange.min = "1";
      zoomRange.max = String(DIGITAL_ZOOM_MAX);
      zoomRange.step = "0.1";
      zoomRange.value = "1";
      zoomMode.textContent = "(ซูมดิจิทัล)";
    }
    zoomRange.disabled = false;
    showZoom();
  }

  function showZoom() {
    zoomValue.textContent = `${Number(zoomRange.value).toFixed(1)}x`;
  }

  zoomRange.addEventListener("input", async () => {
    showZoom();
    const value = Number(zoomRange.value);
    if (hardwareZoom) {
      try {
        await stream.getVideoTracks()[0].applyConstraints({ advanced: [{ zoom: value }] });
      } catch { /* บางรุ่นปฏิเสธบางค่า ไม่เป็นไร */ }
    } else {
      digitalZoom = value;
      video.style.transform = value > 1 ? `scale(${value})` : ""; // ให้พรีวิวตรงกับภาพที่ส่ง
    }
  });

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
    video.style.transform = "";
    digitalZoom = 1;
    zoomRange.disabled = true;
    lensSelect.disabled = true;
    zoomMode.textContent = "";
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
      await openCamera(readSavedLens());
      await listLenses();

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
    // ซูมดิจิทัล: ครอปพื้นที่กลางภาพขนาด 1/zoom แล้วย่อลงเป็นกว้างไม่เกิน 640px
    const srcW = video.videoWidth / digitalZoom;
    const srcH = video.videoHeight / digitalZoom;
    const srcX = (video.videoWidth - srcW) / 2;
    const srcY = (video.videoHeight - srcH) / 2;
    const scale = Math.min(1, FRAME_WIDTH / srcW);
    canvas.width = Math.round(srcW * scale);
    canvas.height = Math.round(srcH * scale);
    context.drawImage(video, srcX, srcY, srcW, srcH, 0, 0, canvas.width, canvas.height);
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
