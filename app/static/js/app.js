// app/static/js/app.js

document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ FastAPI Base Template Loaded");

  // 현재 페이지 경로 로그
  console.log("📍 Current path:", window.location.pathname);

  // 간단한 메시지 표시 (예: header 밑에 표시)
  const main = document.querySelector("main");
  const infoBar = document.createElement("div");
  infoBar.style.marginTop = "12px";
  infoBar.style.padding = "8px 12px";
  infoBar.style.background = "#f3f4f6";
  infoBar.style.borderRadius = "8px";
  infoBar.textContent = "FastAPI와 연결된 JS 동작 중 🚀";
  main.prepend(infoBar);

});
