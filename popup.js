"use strict";

const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");

browser.storage.local.get({ apiKey: "" }).then(({ apiKey }) => {
  if (apiKey.trim()) {
    statusDot.classList.add("ok");
    statusText.textContent = "Hazır — API anahtarı ayarlandı";
  } else {
    statusDot.classList.add("warn");
    statusText.textContent = "API anahtarı eksik — Ayarlara git";
  }
});

document.getElementById("open-settings").addEventListener("click", () => {
  browser.runtime.openOptionsPage();
});
