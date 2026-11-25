(() => {
  const video = document.getElementById("camera-video");
  const startButton = document.getElementById("start-camera");
  const stopButton = document.getElementById("stop-camera");
  const status = document.getElementById("connection-status");
  const fpsLabel = document.getElementById("fps-value");
  const placeholder = document.getElementById("video-placeholder");
  const errorLabel = document.getElementById("camera-error");
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d", { alpha: false });
  const targetFps = 5;

  let stream = null;
  let socket = null;
  let sendTimer = null;
  let sentFrames = 0;
  let fpsTimer = null;

  function setStatus(text, connected = false) {
    status.textContent = text;
    status.classList.toggle("is-ok", connected);
  }

  function stop() {
    if (sendTimer !== null) window.clearInterval(sendTimer);
    if (fpsTimer !== null) window.clearInterval(fpsTimer);
    sendTimer = null;
    fpsTimer = null;
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
    setStatus("หยุดส่งภาพ");
  }

  async function start() {
    errorLabel.textContent = "";
    startButton.disabled = true;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 } },
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
        const interval = 1000 / targetFps;
        sendTimer = window.setInterval(sendFrame, interval);
        fpsTimer = window.setInterval(() => {
          fpsLabel.textContent = String(sentFrames);
          sentFrames = 0;
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
    const scale = Math.min(1, 640 / video.videoWidth);
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (blob && socket && socket.readyState === WebSocket.OPEN) {
        blob.arrayBuffer().then((buffer) => {
          if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(buffer);
            sentFrames += 1;
          }
        });
      }
    }, "image/jpeg", 0.7);
  }

  startButton.addEventListener("click", start);
  stopButton.addEventListener("click", stop);
})();
