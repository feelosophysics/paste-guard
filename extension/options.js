const $ = (id) => document.getElementById(id);
const DEFAULTS = { enabled: true, server: "http://localhost:8787", useLlm: true };

chrome.storage.sync.get(DEFAULTS).then((v) => {
  $("enabled").checked = v.enabled;
  $("server").value = v.server;
  $("useLlm").checked = v.useLlm;
});

$("save").onclick = async () => {
  await chrome.storage.sync.set({
    enabled: $("enabled").checked,
    server: $("server").value.trim() || DEFAULTS.server,
    useLlm: $("useLlm").checked,
  });
  $("status").textContent = "저장했습니다.";
};

$("test").onclick = async () => {
  const server = ($("server").value.trim() || DEFAULTS.server).replace(/\/$/, "");
  try {
    const h = await (await fetch(`${server}/health`)).json();
    $("status").textContent = `연결됨 · LLM: ${h.llm ?? "없음(규칙만 사용)"}`;
  } catch (e) {
    $("status").textContent = `연결 실패: ${e.message}`;
  }
};
