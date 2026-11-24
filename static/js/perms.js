/* Ruxsatlar matritsasi (bo'lim × amal). Server har bir so'rovni o'zi qayta tekshiradi. */
(function () {
"use strict";
const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const csrf = () => (($("meta[name=csrf]") || {}).content || "");
const toast = (m, k) => window.KM && KM.toast ? KM.toast(m, k) : 0;

async function pj(url, data) {
  const r = await fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf(), "X-Requested-With": "fetch" }, body: JSON.stringify(data) });
  let j = {}; try { j = await r.json() } catch (e) {} if (!r.ok || j.ok === false) throw new Error(j.error || "Xatolik yuz berdi"); return j;
}

function level(row) {
  const all = $$("input", row), on = all.filter(i => i.checked).map(i => i.dataset.act);
  if (!on.length) return "hidden";
  if (on.length === all.length) return "full";
  if (on.length === 1 && on[0] === "view") return "read";
  return "part";
}
function refresh(box) {
  $$(".pmr", box).forEach(r => { r.dataset.level = level(r);
    const v = $("input[data-act=view]", r); $$(".pmk:not(.v)", r).forEach(k => k.classList.toggle("off", !!v && !v.checked && false)) });
  const cnt = { full: 0, part: 0, read: 0, hidden: 0 }; $$(".pmr", box).forEach(r => cnt[r.dataset.level]++);
  Object.entries(cnt).forEach(([k, n]) => { const e = $(`[data-pm-n=${k}]`); if (e) e.textContent = n });
}
/* mantiq: yozish amali yoqilsa — ko'rish ham yoqiladi; ko'rish o'chirilsa — hammasi o'chadi */
function logic(inp) {
  const row = inp.closest(".pmr"), v = $("input[data-act=view]", row);
  if (inp.dataset.act === "view" && !inp.checked) $$("input", row).forEach(i => i.checked = false);
  if (inp.dataset.act !== "view" && inp.checked && v) v.checked = true;
}
function grantsOf(box) {
  const g = {}; $$(".pmr", box).forEach(r => { g[r.dataset.code] = $$("input", r).filter(i => i.checked).map(i => i.dataset.act) }); return g;
}
function apply(box, grants) {
  $$(".pmr", box).forEach(r => { const a = grants[r.dataset.code] || []; $$("input", r).forEach(i => i.checked = a.includes(i.dataset.act)) }); refresh(box);
}

document.addEventListener("change", e => {
  const t = e.target;
  if (t.matches("[data-perm-custom]")) { const w = t.closest("[data-when]"); $$(".pmx,.rolehint", w).forEach(x => x.style.display = t.checked ? "" : "none"); return }
  if (!t.matches(".pmx input")) return;
  const box = t.closest(".pmx"); logic(t); refresh(box);
  const url = box.dataset.permLive; if (!url) return;
  const before = grantsOf(box);
  pj(url, { grants: before }).then(j => { apply(box, j.grants); toast(t.checked ? "Ruxsat berildi" : "Ruxsat olib tashlandi") })
    .catch(er => { t.checked = !t.checked; logic(t); refresh(box); toast(er.message, "x") });
});
document.addEventListener("click", e => {
  const b = e.target.closest("[data-perm-bulk],[data-perm-reset]"); if (!b) return;
  const box = $(".pmx[data-perm-live]"); if (!box) return;
  const go = data => pj(box.dataset.permLive, data).then(j => { apply(box, j.grants); toast(j.msg || "Saqlandi") }).catch(er => toast(er.message, "x"));
  if (b.dataset.permReset !== undefined) return go({ reset: 1 });
  const mode = b.dataset.permBulk, g = {};
  $$(".pmr", box).forEach(r => { const acts = $$("input", r).map(i => i.dataset.act);
    g[r.dataset.code] = mode === "all" ? acts : mode === "read" ? acts.filter(a => a === "view") : [] });
  go({ grants: g });
});
document.addEventListener("click", e => {
  const b = e.target.closest("[data-role-save],[data-role-reset]"); if (!b) return;
  const url = b.dataset.roleSave || b.dataset.roleReset, wrap = $(`[data-role-box="${url}"]`), box = $(".pmx", wrap);
  const ap = $(`[data-role-apply="${b.dataset.role}"]`);
  const data = b.dataset.roleReset ? { reset: 1 } : { grants: grantsOf(box), apply_all: !!(ap && ap.checked) };
  pj(url, data).then(j => { apply(box, j.grants); toast(j.msg || "Saqlandi") }).catch(er => toast(er.message, "x"));
});
$$(".pmx").forEach(refresh);
})();
