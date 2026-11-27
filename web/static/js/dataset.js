// หน้า /dataset: แสดงภาพที่เก็บไว้เทรน ML พร้อมป้ายที่ระบบติด และลบภาพที่ป้ายผิด
(() => {
  const $ = (id) => document.getElementById(id);
  const grid = $("sample-grid");
  const errorLabel = $("dataset-error");

  const SOURCE_NAMES = {
    auto_detect: "เดินตามอัตโนมัติ",
    move_done: "กดเดินเสร็จ",
    manual: "บันทึกเอง",
    new_game: "New game",
  };

  function showSummary(data) {
    const c = data.counts || {};
    $("dataset-summary").textContent = data.boards
      ? `${data.boards} ภาพ · ${data.samples} ช่อง (ว่าง ${c.empty} · ขาว ${c.white} · ดำ ${c.black})`
      : "ยังไม่มีข้อมูล";
    $("empty-note").hidden = Boolean(data.boards);
  }

  async function request(path, method = "GET") {
    const response = await fetch(path, { method });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    return payload;
  }

  function card(sample) {
    const item = document.createElement("figure");
    item.className = "sample-card";

    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = `ภาพกระดาน ${sample.id} พร้อมป้าย`;
    img.src = `/api/ml/samples/${encodeURIComponent(sample.id)}/image`;

    const caption = document.createElement("figcaption");
    const info = document.createElement("span");
    info.className = "muted";
    const source = sample.source.startsWith("import:")
      ? `นำเข้า ${sample.source.slice(7)}`
      : SOURCE_NAMES[sample.source] || sample.source;
    info.textContent = `${sample.time.slice(11)} · ${source}`;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "button button-ghost";
    remove.textContent = "ลบ";
    remove.addEventListener("click", async () => {
      remove.disabled = true;
      try {
        const status = await request(`/api/ml/samples/${encodeURIComponent(sample.id)}`, "DELETE");
        item.remove();
        showSummary(status.dataset);
      } catch (error) {
        remove.disabled = false;
        errorLabel.textContent = error.message;
      }
    });
    caption.append(info, remove);
    item.append(img, caption);
    return item;
  }

  async function load() {
    errorLabel.textContent = "";
    try {
      const data = await request("/api/ml/samples");
      showSummary(data);
      grid.replaceChildren(...data.items.map(card));
    } catch (error) {
      errorLabel.textContent = error.message;
    }
  }

  $("reload").addEventListener("click", load);
  $("delete-all").addEventListener("click", async () => {
    if (!window.confirm("ลบข้อมูลเทรนทั้งหมด? กู้คืนไม่ได้")) return;
    try {
      const status = await request("/api/ml/samples", "DELETE");
      grid.replaceChildren();
      showSummary(status.dataset);
    } catch (error) {
      errorLabel.textContent = error.message;
    }
  });

  load();
})();
