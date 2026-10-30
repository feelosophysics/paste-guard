// 페이지 대신 점검 서버를 부른다. 확장 권한으로 호출하므로 사이트의 CORS·사설망 제한을 받지 않는다.
const DEFAULT_SERVER = "http://localhost:8787";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type !== "analyze") return;
  (async () => {
    try {
      const { server = DEFAULT_SERVER, useLlm = true } = await chrome.storage.sync.get(["server", "useLlm"]);
      const blob = await (await fetch(msg.dataUrl)).blob();
      const form = new FormData();
      form.append("file", blob, "paste.png");
      const res = await fetch(`${server.replace(/\/$/, "")}/analyze?use_llm=${useLlm}`, { method: "POST", body: form });
      if (!res.ok) throw new Error(`서버 응답 ${res.status}`);
      sendResponse({ ok: true, result: await res.json() });
    } catch (e) {
      sendResponse({ ok: false, error: String(e.message || e) });
    }
  })();
  return true; // 비동기 응답
});
