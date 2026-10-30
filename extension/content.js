// Paste Guard 콘텐츠 스크립트
// 1) 이미지 붙여넣기를 사이트보다 먼저 받아 막는다
// 2) 점검 서버에서 노출 후보를 받아 미리 선택된 채 보여 준다
// 3) 사용자가 확인하면 고른 영역을 가린 이미지로 붙여넣기를 다시 일으킨다
// 확장 없이 데모 페이지에 <script>로 넣어도 동작한다(window.PASTE_GUARD_SERVER로 서버를 직접 부름).
(() => {
  const root = document.documentElement;
  if (!root || root.dataset.pasteGuard) return; // 확장과 데모 스크립트가 함께 있으면 한 번만 동작
  root.dataset.pasteGuard = "on";

  const IN_EXTENSION = typeof chrome !== "undefined" && !!chrome.runtime?.id;
  const ours = new WeakSet(); // 우리가 다시 일으킨 붙여넣기는 통과시킨다
  let enabled = true;

  if (IN_EXTENSION) {
    chrome.storage.sync.get({ enabled: true }).then((v) => (enabled = v.enabled));
    chrome.storage.onChanged.addListener((c) => c.enabled && (enabled = c.enabled.newValue));
  }

  window.addEventListener("paste", onPaste, true);

  // ---- 붙여넣기 가로채기 -------------------------------------------------------

  function onPaste(e) {
    if (!enabled || ours.has(e)) return;
    const file = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith("image/"));
    if (!file) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    // window에서 받은 e.target은 그림자 DOM 바깥으로 바뀌어 있으므로 실제 입력 위치를 쓴다
    const target = e.composedPath()[0] || e.target;
    review(file, saveCaret(target));
  }

  function saveCaret(target) {
    const el = target.nodeType === 1 ? target : target.parentElement;
    const sel = getSelection();
    return {
      el,
      range: sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null,
      start: el?.selectionStart,
      end: el?.selectionEnd,
    };
  }

  function restoreCaret(c) {
    c.el?.focus?.({ preventScroll: true });
    if (typeof c.start === "number" && c.el.setSelectionRange) {
      c.el.setSelectionRange(c.start, c.end);
    } else if (c.range) {
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(c.range);
    }
  }

  function repaste(caret, file) {
    restoreCaret(caret);
    const dt = new DataTransfer();
    dt.items.add(file);
    const ev = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true, composed: true });
    ours.add(ev);
    (caret.el || document.activeElement || document.body).dispatchEvent(ev);
  }

  // ---- 서버 호출 ---------------------------------------------------------------

  async function analyze(file) {
    if (IN_EXTENSION) {
      const dataUrl = await new Promise((ok, fail) => {
        const r = new FileReader();
        r.onload = () => ok(r.result);
        r.onerror = fail;
        r.readAsDataURL(file);
      });
      const res = await chrome.runtime.sendMessage({ type: "analyze", dataUrl });
      if (!res?.ok) throw new Error(res?.error || "확장 백그라운드 응답 없음");
      return res.result;
    }
    const server = (window.PASTE_GUARD_SERVER || "http://localhost:8787").replace(/\/$/, "");
    const form = new FormData();
    form.append("file", file, file.name || "paste.png");
    const res = await fetch(`${server}/analyze`, { method: "POST", body: form });
    if (!res.ok) throw new Error(`서버 응답 ${res.status}`);
    return res.json();
  }

  // ---- 가림 처리 ---------------------------------------------------------------

  async function mask(file, boxes) {
    const bmp = await createImageBitmap(file);
    const canvas = document.createElement("canvas");
    canvas.width = bmp.width;
    canvas.height = bmp.height;
    const g = canvas.getContext("2d");
    g.drawImage(bmp, 0, 0);
    g.fillStyle = "#000";
    const pad = 3;
    for (const [x0, y0, x1, y1] of boxes) g.fillRect(x0 - pad, y0 - pad, x1 - x0 + pad * 2, y1 - y0 + pad * 2);
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/png"));
    return new File([blob], file.name || "image.png", { type: "image/png" });
  }

  // ---- 점검 화면 ---------------------------------------------------------------

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; font-family: system-ui, "Malgun Gothic", sans-serif; }
    .backdrop { position: fixed; inset: 0; background: rgba(15,18,24,.55); display: flex; align-items: flex-start; justify-content: center; padding-top: 4vh; z-index: 2147483647; }
    .panel { user-select: none; background: #fff; color: #1f2328; border-radius: 12px; width: min(1100px, 94vw); max-height: 92vh; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0,0,0,.35); overflow: hidden; }
    header { padding: 14px 18px; border-bottom: 1px solid #e5e7eb; display: flex; gap: 12px; align-items: baseline; }
    header b { font-size: 16px; }
    header span { color: #57606a; font-size: 13px; }
    .body { display: flex; gap: 16px; padding: 16px 18px; overflow: auto; min-height: 0; }
    .stage { position: relative; flex: 1 1 auto; align-self: flex-start; user-select: none; cursor: crosshair; border: 1px solid #e5e7eb; }
    .stage img { display: block; max-width: 100%; max-height: 70vh; }
    .box { position: absolute; border: 2px dashed #d97706; background: rgba(217,119,6,.08); cursor: pointer; }
    .box.on { border: 2px solid #e11d48; background: rgba(0,0,0,.82); }
    .box.draft { border: 2px dashed #2563eb; background: rgba(37,99,235,.12); pointer-events: none; }
    .list { flex: 0 0 300px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }
    .item { display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; padding: 8px; border: 1px solid #e5e7eb; border-radius: 8px; cursor: pointer; }
    .item.on { border-color: #111; background: #f6f8fa; }
    .item input { grid-row: span 2; margin-top: 2px; }
    .chip { font-weight: 600; }
    .chip small { font-weight: 400; color: #57606a; margin-left: 4px; }
    .text { color: #57606a; word-break: break-all; }
    .hint { color: #57606a; font-size: 12px; }
    footer { padding: 12px 18px; border-top: 1px solid #e5e7eb; display: flex; gap: 8px; justify-content: flex-end; align-items: center; }
    footer .meta { margin-right: auto; color: #57606a; font-size: 12px; }
    button { font-size: 14px; padding: 8px 14px; border-radius: 8px; border: 1px solid #d0d7de; background: #f6f8fa; cursor: pointer; }
    button.primary { background: #111; color: #fff; border-color: #111; }
    .msg { padding: 40px; text-align: center; color: #57606a; }
    .toast { position: fixed; right: 20px; bottom: 20px; background: #111; color: #fff; padding: 10px 14px; border-radius: 8px; font-size: 13px; z-index: 2147483647; }
  `;

  function mount() {
    const host = document.createElement("paste-guard-ui");
    const shadow = host.attachShadow({ mode: "open" });
    shadow.innerHTML = `<style>${CSS}</style>`;
    document.documentElement.appendChild(host);
    return { host, shadow };
  }

  function toast(text) {
    const { host, shadow } = mount();
    shadow.innerHTML += `<div class="toast"></div>`;
    shadow.querySelector(".toast").textContent = text;
    setTimeout(() => host.remove(), 2600);
  }

  async function review(file, caret) {
    const { host, shadow } = mount();
    const url = URL.createObjectURL(file);
    shadow.innerHTML += `
      <div class="backdrop"><div class="panel">
        <header><b>붙여넣기 전 점검</b><span>가릴 영역을 확인하세요</span></header>
        <div class="msg">노출 후보를 찾는 중…</div>
      </div></div>`;
    const panel = shadow.querySelector(".panel");

    const close = () => {
      host.remove();
      URL.revokeObjectURL(url);
    };
    const passOriginal = () => {
      close();
      repaste(caret, file);
    };
    const cancel = () => {
      close();
      restoreCaret(caret);
    };

    let result;
    try {
      result = await analyze(file);
    } catch (err) {
      panel.querySelector(".msg").textContent = `점검 서버에 연결하지 못했습니다: ${err.message}`;
      panel.insertAdjacentHTML("beforeend", `<footer><button data-a="cancel">취소</button><button data-a="orig">원본 그대로 붙여넣기</button></footer>`);
      panel.querySelector('[data-a="cancel"]').onclick = cancel;
      panel.querySelector('[data-a="orig"]').onclick = passOriginal;
      return;
    }

    const items = result.candidates.map((c) => ({ ...c }));
    if (!items.length) {
      close();
      repaste(caret, file);
      toast("노출 후보가 없어 그대로 붙여넣었습니다.");
      return;
    }

    panel.querySelector(".msg").remove();
    panel.insertAdjacentHTML(
      "beforeend",
      `<div class="body">
         <div class="stage"><img alt="붙여넣을 이미지" draggable="false"></div>
         <div class="list"><div class="hint">상자나 목록을 눌러 가림을 켜고 끕니다. 이미지 위를 끌면 영역을 직접 추가합니다.</div></div>
       </div>
       <footer>
         <span class="meta"></span>
         <button data-a="cancel">취소</button>
         <button data-a="orig">원본 붙여넣기</button>
         <button data-a="mask" class="primary">가리고 붙여넣기</button>
       </footer>`
    );
    const stage = panel.querySelector(".stage");
    const list = panel.querySelector(".list");
    stage.querySelector("img").src = url;
    const W = result.width, H = result.height;
    const SOURCE = { rule: "규칙", llm: "AI", manual: "직접" };
    panel.querySelector(".meta").textContent =
      `OCR ${result.timing_ms.ocr}ms · 판정 ${result.timing_ms.judge}ms · AI 판정 ${result.llm === "ok" ? "사용" : result.llm === "off" ? "꺼짐" : result.llm}`;

    function render() {
      stage.querySelectorAll(".box:not(.draft)").forEach((b) => b.remove());
      list.querySelectorAll(".item").forEach((b) => b.remove());
      items.forEach((c) => {
        const [x0, y0, x1, y1] = c.box;
        const box = document.createElement("div");
        box.className = "box" + (c.selected ? " on" : "");
        box.title = `${c.label}: ${c.text}`;
        Object.assign(box.style, {
          left: `${(x0 / W) * 100}%`, top: `${(y0 / H) * 100}%`,
          width: `${((x1 - x0) / W) * 100}%`, height: `${((y1 - y0) / H) * 100}%`,
        });
        box.onmousedown = (ev) => ev.stopPropagation();
        box.onclick = () => { c.selected = !c.selected; render(); };
        stage.appendChild(box);

        const item = document.createElement("label");
        item.className = "item" + (c.selected ? " on" : "");
        item.innerHTML = `<input type="checkbox"><span class="chip"></span><span class="text"></span>`;
        item.querySelector("input").checked = c.selected;
        item.querySelector("input").onchange = (ev) => { c.selected = ev.target.checked; render(); };
        item.querySelector(".chip").textContent = c.label;
        item.querySelector(".chip").insertAdjacentHTML("beforeend", `<small></small>`);
        item.querySelector(".chip small").textContent = `${SOURCE[c.source] || c.source} · ${c.reason}`;
        item.querySelector(".text").textContent = c.text;
        list.appendChild(item);
      });
    }

    // 이미지 위를 끌어 영역을 직접 추가한다
    stage.onmousedown = (ev) => {
      ev.preventDefault(); // 이미지 기본 끌기(드래그 앤 드롭)가 시작되면 mouseup이 오지 않는다
      const rect = stage.getBoundingClientRect();
      const sx = ev.clientX, sy = ev.clientY;
      const draft = document.createElement("div");
      draft.className = "box draft";
      stage.appendChild(draft);
      const clamp = (v, max) => Math.min(Math.max(v, 0), max);
      const toImg = (x, y) => [clamp(((x - rect.left) / rect.width) * W, W), clamp(((y - rect.top) / rect.height) * H, H)];
      const move = (m) => {
        Object.assign(draft.style, {
          left: `${Math.min(sx, m.clientX) - rect.left}px`, top: `${Math.min(sy, m.clientY) - rect.top}px`,
          width: `${Math.abs(m.clientX - sx)}px`, height: `${Math.abs(m.clientY - sy)}px`,
        });
      };
      const up = (u) => {
        window.removeEventListener("mousemove", move, true);
        window.removeEventListener("mouseup", up, true);
        draft.remove();
        if (Math.abs(u.clientX - sx) < 4 || Math.abs(u.clientY - sy) < 4) return;
        const [ax, ay] = toImg(Math.min(sx, u.clientX), Math.min(sy, u.clientY));
        const [bx, by] = toImg(Math.max(sx, u.clientX), Math.max(sy, u.clientY));
        items.push({ id: `m${items.length}`, label: "직접 지정", text: "", box: [ax, ay, bx, by], selected: true, source: "manual", reason: "사용자가 추가" });
        render();
      };
      window.addEventListener("mousemove", move, true);
      window.addEventListener("mouseup", up, true);
    };

    panel.querySelector('[data-a="cancel"]').onclick = cancel;
    panel.querySelector('[data-a="orig"]').onclick = passOriginal;
    panel.querySelector('[data-a="mask"]').onclick = async () => {
      const masked = mask(file, items.filter((c) => c.selected).map((c) => c.box));
      // 다음 붙여넣기도 안전하도록 클립보드도 가린 이미지로 바꾼다(실패해도 진행).
      // ClipboardItem에 Promise를 넘겨야 클릭 직후의 사용자 동작 권한 안에서 쓰기가 시작된다.
      try {
        navigator.clipboard?.write([new ClipboardItem({ "image/png": masked })]).catch(() => {});
      } catch {}
      const file2 = await masked;
      close();
      repaste(caret, file2);
    };
    shadow.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") cancel();
      if (ev.key === "Enter") {
        ev.preventDefault(); // 포커스된 버튼의 기본 Enter 동작까지 겹치면 두 번 붙여넣는다
        panel.querySelector('[data-a="mask"]').click();
      }
    });
    render();
    panel.querySelector('[data-a="mask"]').focus();
  }
})();
