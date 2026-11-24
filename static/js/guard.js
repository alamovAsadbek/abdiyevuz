/* Ekran himoyasi (talaba / yordamchi — sozlamaga qarab).
   Aniq haqiqat: brauzer OS darajasidagi ekran yozish dasturini (OBS, telefon kamerasi) 100% to'xtata olmaydi.
   Shuning uchun: 1) urinishni aniqlash va kontentni darhol yashirish, 2) har bir hodisani serverga yozish va
   asosiy o'qituvchiga xabar berish, 3) butun sahifada ism + ID suv belgisi — sizib chiqqan rasm kimdanligi ko'rinadi. */
(function () {
"use strict";
const body = document.body;
if (!body.dataset.protect || body.dataset.room) return;
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const csrf = () => (($("meta[name=csrf]") || {}).content || "");
const NAME = body.dataset.name || "", UID = body.dataset.uid || "";
const sent = {};

/* ---------- serverga xabar ---------- */
function contentName() {
  const v = $(".vw"), f = $(".pvh,.fview"), h = $(".ph1 h1");
  if (v) return "Video: " + (h ? h.textContent.trim() : "");
  if (f) return "Fayl: " + ((f.closest(".mdl") && $(".mdl h3")) ? $(".mdl h3").textContent.trim() : (h ? h.textContent.trim() : ""));
  if ($("form[data-test-run], .qq")) return "Test: " + (h ? h.textContent.trim() : "");
  return "";
}
function report(kind, meta) {
  const k = kind + location.pathname, now = Date.now();
  if (sent[k] && now - sent[k] < 8000) return;           // bir xil hodisa 8 soniyada bir marta
  sent[k] = now;
  const data = { kind, url: location.pathname + location.search, title: document.title.replace(/ — Abdiyev\.uz$/, ""),
    content: contentName(), screen: screen.width + "×" + screen.height, meta: Object.assign({ vis: document.visibilityState, w: innerWidth, h: innerHeight }, meta || {}) };
  try {
    fetch("/security/incident/", { method: "POST", credentials: "same-origin", keepalive: true,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(), "X-Requested-With": "fetch" }, body: JSON.stringify(data) });
  } catch (_) {}
}
window.KM_GUARD = { report };

/* ---------- kontentni yashirish ---------- */
let shield;
function makeShield() {
  shield = document.createElement("div"); shield.className = "gshield";
  shield.innerHTML = `<div><i data-feather="shield-off"></i><b>Ekranni suratga olish / yozib olish taqiqlangan</b><span>Bu harakat qayd etildi va o‘qituvchiga yuborildi.<br>${esc(NAME)} · ${esc(UID)}</span><button type="button" class="bt w">Tushundim</button></div>`;
  body.appendChild(shield); window.feather && feather.replace();
  shield.querySelector("button").onclick = () => hide(true);
}
function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])) }
let hideT;
function show(ms, sticky) {
  if (!shield) makeShield();
  body.classList.add("bl2", "gon"); shield.classList.add("on"); shield.classList.toggle("st", !!sticky);
  $$("video").forEach(v => { try { if (!v.paused) { v.dataset.gp = 1; v.pause() } } catch (_) {} });
  clearTimeout(hideT); if (!sticky) hideT = setTimeout(() => hide(), ms || 2500);
}
function hide(force) {
  if (!shield || (shield.classList.contains("st") && !force)) return;
  shield.classList.remove("on", "st"); body.classList.remove("gon");
  if (document.hasFocus()) body.classList.remove("bl2");
}
function soft(on) { body.classList.toggle("bl2", on) }   // faqat xiralashtirish (oyna fokusini yo'qotganda)
const hasProtected = () => !!$(".vw,.pvh,.fview,.qq,form[data-test-run]");

/* ---------- klaviatura ---------- */
let metaAt = 0, shiftMetaAt = 0;
document.addEventListener("keydown", e => {
  const k = (e.key || "").toLowerCase(), c = e.code || "", ctrl = e.ctrlKey || e.metaKey;
  if (k === "meta" || k === "os") metaAt = Date.now();
  if (e.metaKey && e.shiftKey) shiftMetaAt = Date.now();
  if (k === "printscreen" || c === "PrintScreen") { e.preventDefault(); show(3000); report("printscreen"); return }
  // macOS: Cmd+Shift+3/4/5/6 — skrinshot / ekran yozish
  if (e.metaKey && e.shiftKey && /Digit[3456]/.test(c)) { e.preventDefault(); show(4000, true); report(c === "Digit5" ? "record" : "snip", { key: "Cmd+Shift+" + c.slice(5) }); return }
  // Windows: Win+Shift+S (Ножницы), Win+Alt+R / Win+G (Xbox Game Bar yozish)
  if (e.metaKey && e.shiftKey && k === "s") { e.preventDefault(); show(4000, true); report("snip", { key: "Win+Shift+S" }); return }
  if (e.metaKey && e.altKey && (k === "r" || k === "printscreen")) { show(4000, true); report("record", { key: "Win+Alt+" + k.toUpperCase() }); return }
  if (e.metaKey && k === "g") { show(3000, true); report("record", { key: "Win+G" }); return }
  if (k === "f12" || (ctrl && e.shiftKey && ["i", "j", "c", "k"].includes(k)) || (e.metaKey && e.altKey && ["i", "j", "c", "u"].includes(k))) { e.preventDefault(); report("devtools", { key: e.key }); return }
  if (ctrl && k === "p") { e.preventDefault(); show(2500); report("print"); return }
  if (ctrl && k === "s") { e.preventDefault(); report("save"); return }
  if (ctrl && k === "u") { e.preventDefault(); report("source"); return }
  if (ctrl && (k === "c" || k === "x") && !isEditable(e.target)) { if (hasProtected()) { e.preventDefault(); report("copy") } }
}, true);
document.addEventListener("keyup", e => {
  if (e.key === "PrintScreen" || e.code === "PrintScreen") { try { navigator.clipboard.writeText(`© Abdiyev.uz — ${NAME} (${UID}) — nusxa olish taqiqlangan`) } catch (_) {} show(3000); report("printscreen") }
}, true);
function isEditable(t) { return t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) }

/* ---------- oyna fokusi / ko'rinish ---------- */
addEventListener("blur", () => {
  soft(true);
  const d = Date.now() - Math.max(metaAt, shiftMetaAt);
  if (d < 1500) { show(4000, true); report("snip", { detail: "Win tugmasidan so‘ng oyna fokusni yo‘qotdi" }) }   // Win+Shift+S ko'pincha shunday ko'rinadi
  else if (hasProtected()) report("blur");
});
addEventListener("focus", () => { if (!shield || !shield.classList.contains("on")) soft(false) });
document.addEventListener("visibilitychange", () => { if (document.hidden) { soft(true); $$("video").forEach(v => { try { v.pause() } catch (_) {} }) } else if (document.hasFocus()) soft(false) });
addEventListener("beforeprint", () => { show(3000); report("print") });

/* ---------- nusxalash, o'ng tugma, sudrash ---------- */
document.addEventListener("copy", e => { if (!isEditable(e.target) && hasProtected()) { e.preventDefault(); try { e.clipboardData.setData("text/plain", `© Abdiyev.uz — ${NAME} (${UID})`) } catch (_) {} report("copy") } });
document.addEventListener("contextmenu", e => { if (!isEditable(e.target)) { e.preventDefault(); if (e.target.closest(".vw,.pvh,.fview,.qq")) report("context") } });
document.addEventListener("dragstart", e => { if (!isEditable(e.target)) e.preventDefault() });
document.addEventListener("selectstart", e => { if (!isEditable(e.target) && e.target.closest && e.target.closest(".vw,.pvh,.fview,.qq")) e.preventDefault() });

/* ---------- sahifa ichidan ekranni ushlash (getDisplayMedia) ---------- */
try {
  const md = navigator.mediaDevices;
  if (md && md.getDisplayMedia) { const orig = md.getDisplayMedia.bind(md);
    md.getDisplayMedia = function () { report("capture"); show(4000, true); return orig.apply(null, arguments) } }
} catch (_) {}

/* ---------- DevTools ochiqligi (taxminiy: oyna o'lchami farqi) ---------- */
let devOpen = false;
setInterval(() => {
  const dw = outerWidth - innerWidth, dh = outerHeight - innerHeight;
  const open = (dw > 200 || dh > 260) && outerWidth > 500 && devicePixelRatio <= 2;
  if (open && !devOpen) { report("devtools", { detail: `oyna farqi ${dw}×${dh}` }); if (hasProtected()) soft(true) }
  if (!open && devOpen && document.hasFocus()) soft(false);
  devOpen = open;
}, 2000);

/* ---------- butun sahifa suv belgisi ---------- */
if (body.dataset.wm) {
  const w = document.createElement("div"); w.className = "gwm"; w.setAttribute("aria-hidden", "true");
  const t = new Date().toLocaleDateString("ru");
  let h = ""; for (let i = 0; i < 40; i++) h += `<span>${esc(NAME)} · ${esc(UID)} · ${t}</span>`;
  w.innerHTML = h; body.appendChild(w);
  // suv belgisi o'chirilsa — qayta qo'shiladi va hodisa yoziladi
  new MutationObserver(() => { if (!document.body.contains(w)) { body.appendChild(w); report("devtools", { detail: "suv belgisi o‘chirildi" }) } }).observe(body, { childList: true });
}
})();
