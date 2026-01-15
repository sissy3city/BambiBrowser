chrome.runtime.onInstalled.addListener(() => {
  chrome.tabs.create({ url: chrome.runtime.getURL("setup.html") });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.tabs.create({ url: "https://hypnotube.com" });
});