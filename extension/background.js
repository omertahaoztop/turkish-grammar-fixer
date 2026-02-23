"use strict";

browser.contextMenus.create({
  id: "fix-turkish",
  title: "Türkçe yazımı düzelt",
  contexts: ["selection"],
});

browser.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== "fix-turkish") return;

  browser.tabs.sendMessage(tab.id, {
    type: "FIX_SELECTION",
    selectedText: info.selectionText,
  });
});
