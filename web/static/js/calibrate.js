// หน้า /calibrate: คลิก/ลาก 4 มุมกระดานบนภาพล่าสุดจากกล้อง แล้วบันทึกไปที่เซิร์ฟเวอร์
// พิกัดเก็บแบบสัดส่วน 0–1 ของขนาดภาพ (x / ความกว้าง, y / ความสูง)
(() => {
  const $ = (id) => document.getElementById(id);
  const canvas = $("corner-canvas");
  const context = canvas.getContext("2d");
  const CORNER_NAMES = ["ซ้ายบน", "ขวาบน", "ขวาล่าง", "ซ้ายล่าง"];
  const HANDLE_RADIUS = 14; // รัศมีจุดจับ (พิกเซลบนจอ) สำหรับคลิกลาก

  let image = null;        // ภาพล่าสุดจากกล้อง (HTMLImageElement)
  let corners = [];        // [[x, y], ...] แบบสัดส่วน 0–1 สูงสุด 4 จุด
  let dragIndex = -1;      // จุดที่กำลังลาก (-1 = ไม่ได้ลาก)
  let previewTimer = null;

  const whiteSide = () => document.querySelector('input[name="white-side"]:checked').value;

  function setError(text) { $("calibrate-error").textContent = text || ""; }
  function setMessage(text) { $("calibrate-message").textContent = text || ""; }

  // ---------- วาดภาพ + จุดมุม + กรอบ ----------
  function cssColor(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function draw() {
    if (!image) return;
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    const accent = cssColor("--accent");
    // ขนาดเส้น/ตัวอักษรคิดจากอัตราส่วนภาพจริงต่อขนาดที่แสดง เพื่อให้หนาเท่ากันทุกจอ
    const scale = canvas.width / canvas.getBoundingClientRect().width || 1;
    const points = corners.map(([x, y]) => [x * canvas.width, y * canvas.height]);

    context.strokeStyle = accent;
    context.lineWidth = 2 * scale;
    if (points.length > 1) {
      context.beginPath();
      points.forEach(([x, y], i) => (i ? context.lineTo(x, y) : context.moveTo(x, y)));
      if (points.length === 4) context.closePath();
      context.stroke();
    }
    points.forEach(([x, y], i) => {
      context.beginPath();
      context.arc(x, y, 9 * scale, 0, Math.PI * 2);
      context.fillStyle = accent;
      context.fill();
      context.fillStyle = "#FFFFFF";
      context.font = `600 ${11 * scale}px system-ui, sans-serif`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(String(i + 1), x, y);
    });

    $("step-label").textContent =
      corners.length < 4 ? `คลิกมุมที่ ${corners.length + 1}: ${CORNER_NAMES[corners.length]}` : "ครบ 4 มุม · ลากเพื่อปรับ";
    $("step-label").classList.toggle("is-ok", corners.length === 4);
    $("save-calibration").disabled = corners.length !== 4;
  }

  window.addEventListener("themechange", draw);

  // ---------- แปลงตำแหน่งเมาส์/นิ้ว → พิกัดสัดส่วน ----------
  function pointerToNormalized(event) {
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width;
    const y = (event.clientY - rect.top) / rect.height;
    return [Math.min(1, Math.max(0, x)), Math.min(1, Math.max(0, y))];
  }

  function findHandle(event) {
    const rect = canvas.getBoundingClientRect();
    return corners.findIndex(([x, y]) => {
      const dx = x * rect.width - (event.clientX - rect.left);
      const dy = y * rect.height - (event.clientY - rect.top);
      return Math.hypot(dx, dy) <= HANDLE_RADIUS;
    });
  }

  canvas.addEventListener("pointerdown", (event) => {
    if (!image) return;
    dragIndex = findHandle(event);
    if (dragIndex === -1 && corners.length < 4) {
      corners.push(pointerToNormalized(event));
      dragIndex = corners.length - 1; // ลากต่อได้ทันทีหลังวางจุด
    }
    if (dragIndex !== -1) canvas.setPointerCapture(event.pointerId);
    draw();
  });

  canvas.addEventListener("pointermove", (event) => {
    if (dragIndex === -1) {
      canvas.style.cursor = findHandle(event) !== -1 ? "grab" : corners.length < 4 ? "crosshair" : "default";
      return;
    }
    corners[dragIndex] = pointerToNormalized(event);
    draw();
  });

  canvas.addEventListener("pointerup", () => {
    if (dragIndex !== -1) schedulePreview();
    dragIndex = -1;
  });

  // ---------- ภาพจากกล้อง ----------
  async function loadFrame() {
    setError("");
    try {
      const response = await fetch(`/api/frame/latest.jpg?t=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error("ยังไม่มีภาพจากกล้อง เปิดหน้า /camera บนมือถือแล้วกด \"เริ่มส่งภาพ\" ก่อน");
      const url = URL.createObjectURL(await response.blob());
      const loaded = new Image();
      loaded.onload = () => {
        URL.revokeObjectURL(url);
        image = loaded;
        canvas.width = loaded.naturalWidth;
        canvas.height = loaded.naturalHeight;
        canvas.hidden = false;
        $("canvas-placeholder").hidden = true;
        draw();
        schedulePreview();
      };
      loaded.src = url;
    } catch (error) {
      $("canvas-placeholder").textContent = error.message;
      $("canvas-placeholder").hidden = false;
    }
  }

  // ---------- ตัวอย่างผลลัพธ์ (ดัดภาพบนเซิร์ฟเวอร์ แต่ยังไม่บันทึก) ----------
  function schedulePreview() {
    window.clearTimeout(previewTimer);
    if (corners.length === 4 && image) previewTimer = window.setTimeout(loadPreview, 250);
  }

  async function loadPreview() {
    $("preview-status").textContent = "กำลังดัดภาพ…";
    try {
      const response = await fetch("/api/calibration/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corners, white_side: whiteSide() }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || `HTTP ${response.status}`);
      const url = URL.createObjectURL(await response.blob());
      const preview = $("preview-image");
      preview.onload = () => URL.revokeObjectURL(url);
      preview.src = url;
      preview.hidden = false;
      $("preview-placeholder").hidden = true;
      $("preview-status").textContent = "";
    } catch (error) {
      $("preview-status").textContent = "";
      setError(error.message);
    }
  }

  // ---------- ปุ่ม ----------
  $("refresh-frame").addEventListener("click", loadFrame);

  $("clear-corners").addEventListener("click", () => {
    corners = [];
    $("preview-image").hidden = true;
    $("preview-placeholder").hidden = false;
    draw();
  });

  $("auto-detect").addEventListener("click", async () => {
    setError("");
    setMessage("กำลังหามุมด้วย Canny + Hough…");
    try {
      const response = await fetch("/api/calibration/auto", { method: "POST" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      corners = payload.corners;
      setMessage("พบมุมแล้ว ตรวจดูว่าตรงขอบช่องหมากรุกไหม ถ้าไม่ตรงให้ลากปรับ");
      draw();
      schedulePreview();
    } catch (error) {
      setMessage("");
      setError(error.message);
    }
  });

  document.querySelectorAll('input[name="white-side"]').forEach((radio) => {
    radio.addEventListener("change", schedulePreview);
  });

  $("save-calibration").addEventListener("click", async () => {
    setError("");
    try {
      const response = await fetch("/api/calibration", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ corners, white_side: whiteSide() }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      setMessage("บันทึกแล้ว หน้า Board จะแสดงภาพดัดตรงพร้อมตารางทันที");
    } catch (error) {
      setError(error.message);
    }
  });

  // ---------- เริ่มต้น: โหลดค่าที่เคยบันทึก แล้วโหลดภาพ ----------
  (async () => {
    try {
      const saved = await (await fetch("/api/calibration")).json();
      if (saved.calibrated) {
        corners = saved.corners;
        const radio = document.querySelector(`input[name="white-side"][value="${saved.white_side}"]`);
        if (radio) radio.checked = true;
        setMessage("โหลดค่าที่บันทึกไว้แล้ว ปรับแล้วกดบันทึกอีกครั้งได้");
      }
    } catch {
      // ไม่มีค่าเดิมก็เริ่มใหม่ได้ตามปกติ
    }
    loadFrame();
  })();
})();
