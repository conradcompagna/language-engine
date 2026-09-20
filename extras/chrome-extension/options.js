const KEYS = {
  triggerLazy: "le_trigger_lazy",
};

const $ = (id) => document.getElementById(id);

async function _load() {
  const stored = await chrome.storage.sync.get(Object.values(KEYS));
  $("trigger-lazy").checked = stored[KEYS.triggerLazy] !== false;
}

document.getElementById("settings-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const status = $("save-status");
  await chrome.storage.sync.set({
    [KEYS.triggerLazy]: $("trigger-lazy").checked,
  });
  status.classList.remove("error");
  status.textContent = "Saved.";
  setTimeout(() => { status.textContent = ""; }, 2000);
});

_load();
