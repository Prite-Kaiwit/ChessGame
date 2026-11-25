// สลับธีม Light / Dark และจำค่าไว้ใน localStorage
// โหลดไฟล์นี้ใน <head> (ไม่ใช่ module) เพื่อกำหนดธีมก่อนหน้าเว็บวาดครั้งแรก จะได้ไม่กะพริบ
(() => {
  const STORAGE_KEY = "chessgame-theme";
  const root = document.documentElement;

  // อ่านค่าที่เคยเลือก ถ้าเบราว์เซอร์ปิด storage (เช่นโหมดส่วนตัว) ให้ข้ามไปเงียบๆ
  function readSaved() {
    try {
      const value = localStorage.getItem(STORAGE_KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch {
      return null;
    }
  }

  function save(theme) {
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // บันทึกไม่ได้ก็ยังใช้ธีมได้ตามปกติ แค่ไม่จำค่า
    }
  }

  // ยังไม่เคยเลือก: ใช้ตามการตั้งค่าของระบบปฏิบัติการ
  const systemTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  root.dataset.theme = readSaved() || systemTheme;

  function apply(theme) {
    root.dataset.theme = theme;
    save(theme);
    updateButtons();
    // แจ้งสคริปต์อื่น (เช่น board.js ต้องเปลี่ยนสีลูกศรตามธีม)
    window.dispatchEvent(new CustomEvent("themechange", { detail: theme }));
  }

  // ปุ่มแบบสองตัวเลือก: <div class="theme-toggle"><button data-theme-value="light">…
  function updateButtons() {
    document.querySelectorAll("[data-theme-value]").forEach((button) => {
      const active = button.dataset.themeValue === root.dataset.theme;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-theme-value]").forEach((button) => {
      button.addEventListener("click", () => apply(button.dataset.themeValue));
    });
    updateButtons();
  });
})();
