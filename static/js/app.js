/* Abdiyev.uz — umumiy klient kodi. Inline handlerlar yo'q (CSP: script-src 'self'). */
(function () {
    "use strict";
    const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
    const csrf = () => (($("meta[name=csrf]") || {}).content || "");
    const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    }[c]));
    const I = n => `<i data-feather="${n}"></i>`;
    const body = document.body, ROLE = body.dataset.role || "";
    const K = window.KM = {};

    /* ---------- umumiy yordamchilar ---------- */
    function fx(root) {
        window.feather && feather.replace();
        $$("[data-n]", root).forEach(e => {
            if (e.dataset.done) return;
            e.dataset.done = 1;
            const n = +e.dataset.n, t0 = performance.now();
            (function f(t) {
                const k = Math.min(1, (t - t0) / 1000);
                e.textContent = Math.round(n * (1 - Math.pow(1 - k, 3))).toLocaleString("ru");
                k < 1 && requestAnimationFrame(f)
            })(t0)
        });
        $$(".pvh:not([data-d])", root).forEach(viewer);
        $$("input[data-phone]", root).forEach(e => {
            if (!e.dataset.pm) {
                e.dataset.pm = 1;
                e.addEventListener("input", () => phone(e))
            }
        });
        $$(".vp[data-hls]:not([data-d])", root).forEach(player);
    }

    K.fx = fx;

    function toast(m, kind) {
        const e = document.createElement("div");
        e.className = "tt c " + (kind || "");
        e.innerHTML = I(kind === "x" ? "alert-circle" : "check-circle") + "<span></span>";
        e.lastChild.textContent = m;
        document.body.appendChild(e);
        fx();
        setTimeout(() => e.remove(), 3200);
    }

    K.toast = toast;

    function ov(h, c) {
        $("#ov").innerHTML = h ? `<div class="mdl ${c || ""}"><div class="c">${h}</div></div>` : "";
        fx($("#ov"));
    }

    K.ov = ov;
    const closeOv = () => ov("");

    function ask(msg, fn) {
        ov(`<h3>Tasdiqlang</h3><p class="m" style="margin:8px 0 20px"></p><div class="row"><button class="bt d" data-yes>${I("check")} Ha, davom etish</button><button class="bt s" data-close>Bekor qilish</button></div>`, "ct");
        $("#ov p").textContent = msg;
        $("#ov [data-yes]").onclick = () => {
            closeOv();
            fn()
        };
    }

    K.ask = ask;

    function postForm(url, fields) {
        const f = document.createElement("form");
        f.method = "post";
        f.action = url;
        const add = (k, v) => {
            const i = document.createElement("input");
            i.type = "hidden";
            i.name = k;
            i.value = v;
            f.appendChild(i)
        };
        add("csrfmiddlewaretoken", csrf());
        Object.entries(fields || {}).forEach(([k, v]) => add(k, v));
        document.body.appendChild(f);
        f.submit();
    }

    async function pj(url, data) {
        const r = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {"Content-Type": "application/json", "X-CSRFToken": csrf(), "X-Requested-With": "fetch"},
            body: JSON.stringify(data)
        });
        let j = {};
        try {
            j = await r.json()
        } catch (e) {
        }
        if (!r.ok || j.ok === false) throw new Error(j.error || "Xatolik yuz berdi");
        return j;
    }

    const gj = async u => {
        const r = await fetch(u, {credentials: "same-origin", headers: {"X-Requested-With": "fetch"}});
        if (!r.ok) throw new Error("Xatolik");
        return r.json()
    };
    const jsonData = id => {
        const e = document.getElementById(id);
        try {
            return JSON.parse(e.textContent)
        } catch (_) {
            return []
        }
    };

    function phone(e) {
        let d = e.value.replace(/\D/g, "");
        if (d.startsWith("998")) d = d.slice(3);
        d = d.slice(0, 9);
        const p = [d.slice(0, 2), d.slice(2, 5), d.slice(5, 7), d.slice(7, 9)].filter(Boolean);
        e.value = d ? "+998 " + p.join(" ") : ""
    }

    const copy = t => {
        try {
            return navigator.clipboard.writeText(t).then(() => true, () => false)
        } catch (_) {
            return Promise.resolve(false)
        }
    };
    const ini = n => (n || "?").split(" ").map(x => x[0]).join("").slice(0, 2);

    /* ---------- tanlash oynasi (picker) ---------- */
    function pick(o) {
        const st = {sel: [], items: o.items};
        ov(`<h3 style="margin-bottom:12px">${esc(o.title)}</h3><div class="sr" style="max-width:none;margin-bottom:10px"><input id="pkq" placeholder="Qidirish (ism, ID)…"><span>${I("search")}</span></div><div id="pkl" style="max-height:320px;overflow:auto"></div><div class="row mt"><button class="bt s" data-close>Bekor qilish</button>${o.all ? `<button class="bt s" id="pka">Hammasini tanlash</button>` : ""}<div class="sp"></div><button class="bt" id="pkb"></button></div>`, "ct wd");
        const render = () => {
            const q = $("#pkq").value.toLowerCase();
            $("#pkl").innerHTML = st.items.filter(x => ((x.t || "") + " " + (x.s || "")).toLowerCase().includes(q)).map(x => `<div class="ls ${x.off ? "lk" : ""} ${st.sel.includes(x.id) ? "sl" : ""}" data-id="${x.id}">${x.off ? "" : `<span class="ck ${o.multi ? "" : "r"} ${st.sel.includes(x.id) ? "on" : ""}">${I("check")}</span>`}${x.ic ? `<span class="ic" style="background:var(--p2)">${I(x.ic)}</span>` : `<div class="av">${esc(ini(x.t))}</div>`}<span class="sp"><b>${esc(x.t)}</b><div class="m">${esc(x.s || "")}</div>${x.tg ? `<div style="margin-top:4px"><span class="tag ${x.tc || ""}">${esc(x.tg)}</span></div>` : ""}</span></div>`).join("") || `<div class="m" style="padding:12px">Hech narsa topilmadi</div>`;
            const b = $("#pkb");
            b.innerHTML = esc(o.btn || "Davom etish") + (o.multi ? ` (${st.sel.length})` : "");
            b.disabled = !st.sel.length && !o.allowEmpty;
            fx($("#ov"));
        };
        $("#pkq").oninput = render;
        $("#pkl").onclick = e => {
            const r = e.target.closest("[data-id]");
            if (!r) return;
            const id = +r.dataset.id, x = st.items.find(i => i.id === id);
            if (x.off) return;
            st.sel = o.multi ? (st.sel.includes(id) ? st.sel.filter(i => i !== id) : st.sel.concat(id)) : [id];
            render();
        };
        if (o.all) $("#pka").onclick = () => {
            const v = st.items.filter(x => !x.off).map(x => x.id);
            st.sel = st.sel.length === v.length ? [] : v;
            render()
        };
        $("#pkb").onclick = () => {
            closeOv();
            o.cb(st.sel)
        };
        render();
    }

    K.pick = pick;
    const money = n => n ? n.toLocaleString("ru") + " so‘m" : "Bepul";

    /* ---------- kurs berish (modullar to'liq chiqadi) ---------- */
    function giftModules(course, uids, label) {
        const done = mods => ask(`${uids.length} ta talabaga “${course.title}”${mods === "all" ? "" : " — tanlangan modullar"} to‘lovsiz ochib berilsinmi?`, async () => {
            try {
                await pj("/staff/gift/", {uids, course: course.id, modules: mods});
                toast("Kurs ochib berildi, talabaga xabarnoma yuborildi");
                setTimeout(() => location.reload(), 700)
            } catch (e) {
                toast(e.message, "x")
            }
        });
        if (!course.modular) return done("all");
        const items = [{
            id: 0,
            t: "Barcha modullar",
            s: course.modules.length + " ta modul · " + course.lessons + " dars",
            ic: "layers",
            tg: "To‘liq kurs",
            tc: "f"
        }]
            .concat(course.modules.map(m => ({
                id: m.id,
                t: m.title,
                s: m.lessons + " dars" + (m.active ? "" : " · noaktiv"),
                ic: "layers",
                off: !!m.owned,
                tg: m.owned ? "Talabada bor" : money(m.price),
                tc: m.owned ? "f" : m.price ? "x" : "f"
            })));
        pick({
            title: `“${course.title}” — modullarni tanlang`, items, multi: true, btn: "Berish", all: true,
            cb: ids => done(ids.includes(0) || ids.length >= course.modules.filter(m => !m.owned).length && !course.modules.some(m => m.owned) ? "all" : ids)
        });
    }

    async function giftFromUser(uid) {
        try {
            const d = await gj("/staff/gift/data/?uid=" + uid);
            if (!d.courses.length) return toast("Ochib beriladigan kurs qolmagan", "x");
            pick({
                title: "Kursni tanlang",
                multi: false,
                btn: "Davom etish",
                items: d.courses.map(c => ({
                    id: c.id,
                    t: c.title,
                    s: (c.modular ? "Modulli kurs · " + c.modules.length + " modul · " : "") + c.lessons + " dars",
                    ic: "play-circle",
                    tg: c.paid ? (c.modular ? "dan " : "") + money(c.price) : "Bepul",
                    tc: c.paid ? "x" : "f"
                })),
                cb: ids => giftModules(d.courses.find(c => c.id === ids[0]), [uid])
            });
        } catch (e) {
            toast(e.message, "x")
        }
    }

    async function giftFromCourse(cid) {
        try {
            const d = await gj("/staff/gift/data/?course=" + cid), c = d.courses.find(x => x.id === cid);
            pick({
                title: "Talabalarni tanlang",
                multi: true,
                all: true,
                btn: "Davom etish",
                items: d.students.map(s => ({id: s.id, t: s.t, s: s.s, off: s.off, tg: s.tg, tc: "f"})),
                cb: ids => giftModules(c, ids)
            });
        } catch (e) {
            toast(e.message, "x")
        }
    }

    /* ---------- boy matn muharriri ---------- */
    const FORM = s => s.replace("<=>", "⇌").replace("->", "→").replace(/([A-Za-z)])(\d+)/g, "$1<sub>$2</sub>").replace(/\^(\d*[+-]?)/g, "<sup>$1</sup>");
    const ED = (ph, html) => `<div class="edw"><div class="tb">${[["bold", "bold"], ["italic", "italic"]].map(x => `<button type="button" data-cmd="${x[0]}">${I(x[1])}</button>`).join("")}<button type="button" data-cmd="subscript">x<sub>2</sub></button><button type="button" data-cmd="superscript">x<sup>2</sup></button>${["→", "⇌", "Δ", "°C", "·"].map(s => `<button type="button" data-ins="${s}">${s}</button>`).join("")}<input class="fi" placeholder="H2SO4, Fe^3+"><button type="button" data-fm>${I("hexagon")} Formula</button><label class="i">${I("image")} Rasm<input type="file" accept="image/*" hidden data-edimg></label></div><div class="ed" contenteditable="true" data-ph="${esc(ph)}">${html || ""}</div></div>`;
    let lastRange = null;
    document.addEventListener("selectionchange", () => {
        const s = getSelection();
        if (s.rangeCount && s.anchorNode) {
            const e = s.anchorNode.nodeType === 1 ? s.anchorNode : s.anchorNode.parentElement;
            if (e && e.closest(".ed")) lastRange = s.getRangeAt(0).cloneRange()
        }
    });

    function edInit(root) {
        $$("[data-editor]", root).forEach(h => {
            if (h.dataset.d) return;
            h.dataset.d = 1;
            h.innerHTML = ED(h.dataset.editor, h.dataset.init ? JSON.parse(h.dataset.init) : "");
            const f = h.closest("form"), name = h.dataset.name;
            if (f && name) f.addEventListener("submit", () => {
                let i = f.querySelector(`input[name="${name}"]`);
                if (!i) {
                    i = document.createElement("input");
                    i.type = "hidden";
                    i.name = name;
                    f.appendChild(i)
                }
                i.value = $(".ed", h).innerHTML
            })
        });
    }

    document.addEventListener("mousedown", e => {
        if (e.target.closest("[data-cmd],[data-ins],[data-fm]")) e.preventDefault()
    });

    /* ---------- test muharriri ---------- */
    let qn = 0;

    function addV(q, val, chk) {
        const vs = $(".vs", q);
        if ($$(".vr", vs).length >= 8) return toast("Eng ko‘pi 8 ta variant", "x");
        const d = document.createElement("div");
        d.className = "row vr";
        d.style.cssText = "align-items:flex-start;flex-wrap:nowrap";
        d.innerHTML = `<span class="vl"></span><input type="radio" name="c${q.dataset.u}" ${chk ? "checked" : ""}><div class="sp">${ED("Variant matni", val)}</div><button type="button" class="ib2 x" style="margin-top:8px" data-delv title="Variantni o‘chirish">${I("x")}</button>`;
        vs.appendChild(d);
        if (!$("input:checked", vs)) $("input", vs).checked = true;
        fx(d);
    }

    function addQ(q) {
        const u = ++qn, d = document.createElement("div");
        d.className = "c p qb";
        d.dataset.u = u;
        d.style.marginTop = "14px";
        d.innerHTML = `<div class="row" style="margin-bottom:10px"><span class="tag qn"></span><span class="sp"></span><button type="button" class="ib2 x" data-delq title="Savolni o‘chirish">${I("trash-2")}</button></div><div class="m" style="margin-bottom:6px">Savol matni</div><div class="qtext">${ED("Savolni yozing…", q ? q.text : "")}</div><div class="m" style="margin:12px 0 6px">Javob variantlari — to‘g‘ri javobni belgilang</div><div class="vs"></div><button type="button" class="bt s" data-addv>${I("plus")} Variant qo‘shish</button><div class="m" style="margin:12px 0 6px">Yechim (natijada ko‘rsatiladi)</div><div class="qsol">${ED("Yechimni yozing…", q ? q.solution : "")}</div>`;
        $("#qs").appendChild(d);
        (q ? q.options : ["", "", "", ""]).forEach((o, j) => addV(d, o, j === (q ? q.correct : 0)));
        fx(d);
    }

    const KROW = (K2, a, sol, img) => `<div class="kr" data-a="${a}"><div class="row" style="flex-wrap:nowrap"><span class="no kn"></span><div class="kb">${Array.from({length: K2}, (_, j) => `<button type="button" class="kbt ${j == a ? "on" : ""}" data-key="${j}">${"ABCDEFGH"[j]}</button>`).join("")}</div><div class="sp"></div><button type="button" class="ib2" data-keysol title="Yechim (ixtiyoriy)">${I("edit-3")}</button><button type="button" class="ib2 x" data-keydel title="O‘chirish">${I("trash-2")}</button></div><div class="ks" style="display:none">${ED("Yechim (ixtiyoriy) — matn yoki formula", sol)}<div class="row" style="margin-top:8px;justify-content:flex-start"><label class="bt s">${I("image")} Yechim rasmi<input type="file" accept="image/*" data-solimg hidden></label><span class="m">${img ? "Rasm yuklangan (yangisini tanlasangiz almashadi)" : ""}</span></div></div></div>`;

    function keyBuild(n, K2, init) {
        const g = $("#kg");
        g.dataset.k = K2;
        g.innerHTML = Array.from({length: n}, (_, i) => KROW(K2, init && init[i] ? init[i].correct : -1, init && init[i] ? init[i].solution : "", init && init[i] && init[i].img)).join("");
        fx(g)
    }

    function serializeTest(f) {
        const mode = (f.querySelector("[name=mode]") || {}).value || "manual";
        if (mode === "file") {
            const rows = $$("#kg .kr");
            f.querySelector("[name=kopts]").value = $("#kg").dataset.k || 4;
            f.querySelector("[name=keys]").value = JSON.stringify(rows.map(r => ({
                correct: +r.dataset.a,
                solution: $(".ed", r).innerHTML.trim()
            })));
            rows.forEach((r, i) => {
                const inp = $("[data-solimg]", r);
                if (inp) inp.name = "solimg_" + i
            });
        } else {
            f.querySelector("[name=payload]").value = JSON.stringify($$(".qb").map(b => ({
                text: $(".qtext .ed", b).innerHTML.trim(),
                options: $$(".vr .ed", b).map(e => e.innerHTML.trim()),
                correct: Math.max(0, $$(".vr", b).findIndex(r => $("input", r).checked)),
                solution: $(".qsol .ed", b).innerHTML.trim()
            })));
        }
    }

    function testInit() {
        const f = $("form[data-test-form]");
        if (!f) return;
        const init = jsonData("test-init"), edit = f.dataset.edit === "1", fileMode = f.dataset.mode === "file";
        if (fileMode) {
            keyBuild(init.length || 20, init[0] ? init[0].options?.length || 4 : 4, init);
            const ko = f.querySelector("#ko");
            if (init[0] && init[0].options) ko.value = init[0].options.length;
            $("#kn").value = init.length
        } else if (init.length) init.forEach(addQ); else if (!edit) addQ();
        f.addEventListener("submit", () => serializeTest(f));
    }

    /* ---------- himoyalangan fayl ko'rish (sahifa-rasm + suv belgisi) ---------- */
    async function viewer(h) {
        h.dataset.d = 1;
        h.innerHTML = `<div class="m" style="padding:20px">Yuklanmoqda…</div>`;
        const {kind, pk} = h.dataset;
        try {
            const info = await gj(`/f/${kind}/${pk}/info/`);
            const s = document.createElement("div");
            s.className = "pvs";
            if (!info.pages) {
                s.innerHTML = `<div class="m" style="padding:24px;text-align:center">Bu fayl turini saytda ko‘rsatib bo‘lmaydi. O‘qituvchidan so‘rang.</div>`
            }
            for (let i = 1; i <= info.pages; i++) {
                const im = new Image();
                im.draggable = false;
                im.loading = "lazy";
                im.alt = "";
                im.src = `/f/${kind}/${pk}/${i}.png`;
                s.appendChild(im)
            }
            h.innerHTML = "";
            h.appendChild(s);
            const id = (body.dataset.name || "MEHMON") + " · " + (body.dataset.uid || "");
            const m = document.createElement("div");
            m.className = "pvm";
            m.innerHTML = Array.from({length: 18}, () => `<span>${esc(id)}</span>`).join("");
            h.appendChild(m);
        } catch (e) {
            h.innerHTML = `<div class="m" style="padding:24px;text-align:center">Faylni ko‘rsatib bo‘lmadi.</div>`
        }
    }

    /* ---------- video pleyer (shifrlangan HLS) ---------- */
    const TM = s => {
        s = Math.floor(s || 0);
        return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0")
    };

    function player(vp) {
        vp.dataset.d = 1;
        const v = $("video", vp), src = vp.dataset.hls;
        if (window.Hls && Hls.isSupported()) {
            const h = new Hls({
                xhrSetup: x => {
                    x.withCredentials = true
                }
            });
            h.loadSource(src);
            h.attachMedia(v)
        } else if (v.canPlayType("application/vnd.apple.mpegurl")) v.src = src;
        const upd = () => {
            const d = v.duration || 0, r = $("input[type=range]", vp);
            if (d && document.activeElement !== r) r.value = Math.round(v.currentTime / d * 1000);
            $(".vt", vp).textContent = TM(v.currentTime) + " / " + TM(d);
            $("[data-k=pp]", vp).innerHTML = I(v.paused ? "play" : "pause");
            window.feather && feather.replace()
        };
        ["timeupdate", "loadedmetadata", "pause", "play"].forEach(ev => v.addEventListener(ev, upd));
        v.addEventListener("click", () => v.paused ? v.play() : v.pause());
        vp.addEventListener("click", e => {
            const b = e.target.closest("[data-k]");
            if (!b) return;
            if (b.dataset.k === "pp") v.paused ? v.play() : v.pause();
            if (b.dataset.k === "sp") {
                const sp = [1, 1.25, 1.5, 2, .75], i = (sp.indexOf(v.playbackRate) + 1) % sp.length;
                v.playbackRate = sp[i];
                b.textContent = sp[i] + "×"
            }
            if (b.dataset.k === "fs") {
                const w = b.closest(".vw");
                document.fullscreenElement ? document.exitFullscreen() : w.requestFullscreen && w.requestFullscreen()
            }
        });
        $("input[type=range]", vp).addEventListener("input", e => {
            if (v.duration) v.currentTime = e.target.value / 1000 * v.duration
        });
    }

    /* ---------- suzuvchi panel (ixtiyoriy) ---------- */
    const PREF = (() => {
        try {
            return Object.assign({act: "top", mode: "cards"}, JSON.parse(localStorage.getItem("km-pref") || "{}"))
        } catch (_) {
            return {act: "top", mode: "cards"}
        }
    })();
    const savePref = () => {
        try {
            localStorage.setItem("km-pref", JSON.stringify(PREF))
        } catch (_) {
        }
        document.cookie = "km_mode=" + PREF.mode + ";path=/;max-age=31536000;samesite=lax"
    };

    function rail() {
        const a = $(".atb");
        if (!a || PREF.act !== "float" || !a.children.length) return;
        const r = document.createElement("div");
        r.className = "rail";
        r.innerHTML = `<div class="rg"></div>` + [...a.children].map(b => {
            const x = b.classList.contains("x");
            const ic = b.querySelector("i").dataset.feather, t = (b.querySelector("span") || b).textContent.trim();
            return `<button class="ra ${x ? "x" : ""}" data-proxy="${[...a.children].indexOf(b)}" aria-label="${esc(t)}">${I(ic)}<span>${esc(t)}</span></button>`
        }).join("");
        a.style.display = "none";
        document.getElementById("app").appendChild(r);
        const g = $(".pg");
        g && g.classList.add("hr");
        try {
            const p = JSON.parse(localStorage.getItem("km-rail") || "null");
            if (p) Object.assign(r.style, {
                left: Math.min(innerWidth - r.offsetWidth - 6, Math.max(6, p.x)) + "px",
                top: Math.min(innerHeight - r.offsetHeight - 6, Math.max(6, p.y)) + "px",
                right: "auto",
                bottom: "auto",
                transform: "none"
            })
        } catch (_) {
        }
        let DR = null, LP = 0;
        r.addEventListener("pointerdown", e => {
            const b = r.getBoundingClientRect();
            DR = {x: e.clientX, y: e.clientY, ox: e.clientX - b.left, oy: e.clientY - b.top, on: 0, id: e.pointerId};
            LP = setTimeout(() => {
                if (DR) {
                    DR.on = 1;
                    r.classList.add("dr");
                    try {
                        r.setPointerCapture(DR.id)
                    } catch (_) {
                    }
                }
            }, 280)
        });
        r.addEventListener("pointermove", e => {
            if (!DR) return;
            if (!DR.on) {
                if (Math.hypot(e.clientX - DR.x, e.clientY - DR.y) > 8) {
                    clearTimeout(LP);
                    DR = null
                }
                return
            }
            Object.assign(r.style, {
                left: Math.min(innerWidth - r.offsetWidth - 6, Math.max(6, e.clientX - DR.ox)) + "px",
                top: Math.min(innerHeight - r.offsetHeight - 6, Math.max(6, e.clientY - DR.oy)) + "px",
                right: "auto",
                bottom: "auto",
                transform: "none"
            });
            e.preventDefault()
        });
        const end = () => {
            clearTimeout(LP);
            if (DR && DR.on) {
                try {
                    localStorage.setItem("km-rail", JSON.stringify({
                        x: parseInt(r.style.left),
                        y: parseInt(r.style.top)
                    }))
                } catch (_) {
                }
                r.classList.remove("dr");
                K.nc = 1;
                setTimeout(() => K.nc = 0, 60)
            }
            DR = null
        };
        r.addEventListener("pointerup", end);
        r.addEventListener("pointercancel", end);
    }

    /* ---------- WebSocket (jonli bildirishnomalar va status) ---------- */
    let ws = null, wsT = 0;

    async function connect() {
        if (!body.dataset.uid) return;
        try {
            await fetch("/auth/ping/", {credentials: "same-origin"})
        } catch (_) {
        }
        const u = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws/live/";
        try {
            ws = new WebSocket(u)
        } catch (_) {
            return
        }
        ws.onopen = () => {
            wsT = 0
        };
        ws.onmessage = ev => {
            let d;
            try {
                d = JSON.parse(ev.data)
            } catch (_) {
                return
            }
            const dot = $("#bell-dot");
            const setUnread = n => {
                if (!dot) return;
                dot.textContent = n;
                dot.hidden = !n
            };
            if (d.type === "hello") setUnread(d.unread);
            if (d.type === "notify" || d.type === "message") {
                setUnread(d.unread);
                toast(d.text, d.important ? "x" : "");
                if ($("[data-live=notifs]")) setTimeout(() => location.reload(), 1200)
            }
            if (d.type === "test_status") {
                const lv = $("[data-live=tests]"), td = $("[data-live-test]");
                if (lv || (td && +td.dataset.liveTest === d.id)) {
                    toast(`“${d.title}” testi holati yangilandi`);
                    setTimeout(() => location.reload(), 900)
                }
            }
            if (d.type === "task_closed") {
                const l = $("[data-live-lesson]");
                if (l && +l.dataset.liveLesson === d.lesson) {
                    toast(`“${d.title}” vazifasi muddati tugadi`, "x");
                    setTimeout(() => location.reload(), 1200)
                }
            }
            if (d.type === "meeting" && $("[data-live=meetings]") && !$("#room")) setTimeout(() => location.reload(), 600);
            if (d.type === "refresh" && $("[data-live=tests]")) setTimeout(() => location.reload(), 500)
        };
        ws.onclose = () => {
            wsT = Math.min(30000, (wsT || 1000) * 2);
            setTimeout(connect, wsT)
        };
        setInterval(() => {
            try {
                ws.readyState === 1 && ws.send(JSON.stringify({type: "ping"}))
            } catch (_) {
            }
        }, 60000);
    }

    /* ---------- himoya (talaba): yozib olish/nusxalashga qarshi choralar ---------- */
    /* talaba/yordamchi himoyasi: static/js/guard.js (body[data-protect]) */
    document.addEventListener("contextmenu", e => {
        if (e.target.closest(".pvh,.fview,.vw")) e.preventDefault()
    });
    document.addEventListener("dragstart", e => {
        if (e.target.closest(".pvh,.fview,.vw")) e.preventDefault()
    });

    /* ---------- shartli ko'rsatish: data-when="name=a|b" ---------- */
    function applyWhen(root) {
        $$("[data-when]", root || document).forEach(el => {
            const [n, vs] = el.dataset.when.split("="), i = $(`[name="${n}"]`);
            el.classList.toggle("hide", !(i && vs.split("|").includes(i.value)))
        });
    }

    function audRefresh() {
        const f = $("form[data-msg-form]");
        if (!f) return;
        const a = $("[name=audience]", f).value;
        $$("[data-aud-pick]").forEach(x => x.classList.toggle("hide", x.dataset.audPick !== a));
        const q = new URLSearchParams({a});
        $$("input[name=groups]", f).forEach(i => q.append("g", i.value));
        $$("input[name=users]", f).forEach(i => q.append("u", i.value));
        gj("/staff/messages/count/?" + q).then(d => {
            $("#mcnt").textContent = "Qabul qiluvchilar: " + d.n + " ta"
        }).catch(() => {
        });
    }

    function pickInto(btn) {
        const name = btn.dataset.field, items = jsonData(btn.dataset.src), f = btn.closest("form"),
            cur = $$(`input[name=${name}]`, f).map(i => +i.value);
        pick({
            title: btn.dataset.title,
            items: items.map(x => ({...x})),
            multi: true,
            all: true,
            btn: "Tanlash",
            allowEmpty: true,
            cb: ids => {
                $$(`input[name=${name}]`, f).forEach(i => i.remove());
                ids.forEach(id => {
                    const i = document.createElement("input");
                    i.type = "hidden";
                    i.name = name;
                    i.value = id;
                    f.appendChild(i)
                });
                $("#" + btn.dataset.tags).innerHTML = ids.map(id => `<span class="tag">${esc((items.find(x => x.id === id) || {}).t)}</span>`).join(" ");
                audRefresh()
            }
        });
        const sel = cur;
        if (sel.length) { /* oldingi tanlov saqlanadi */
        }
    }

    /* ---------- hodisalar ---------- */
    document.addEventListener("click", e => {
        const t = e.target;
        if (K.nc && t.closest(".rail")) {
            e.stopPropagation();
            e.preventDefault();
            return
        }
        if (t.closest("[data-close]") || (t.classList && t.classList.contains("mdl"))) {
            closeOv();
            return
        }
        let b;
        if ((b = t.closest("[data-theme-toggle]"))) {
            const d = document.documentElement, n = d.dataset.theme === "dark" ? "light" : "dark";
            d.dataset.theme = n;
            try {
                localStorage.setItem("km-theme", n)
            } catch (_) {
            }
            $$("[data-theme-toggle] i").forEach(i => i.dataset.feather = n === "dark" ? "sun" : "moon");
            fx();
            return
        }
        if (t.closest("[data-back]")) {
            history.length > 1 ? history.back() : location.href = "/";
            return
        }
        if ((b = t.closest("[data-post]"))) {
            e.preventDefault();
            const go = () => postForm(b.dataset.post, Object.assign({}, b.dataset.fields ? JSON.parse(b.dataset.fields) : {}, b.dataset.next ? {next: b.dataset.next} : {}));
            b.dataset.confirm ? ask(b.dataset.confirm, go) : go();
            return
        }
        if ((b = t.closest("[data-menu]"))) {
            const side = $$(".side .nv").map(a => a.outerHTML.replace('class="nv', 'class="nv')).join("");
            ov(`<h3 style="margin-bottom:12px">Abdiyev.uz</h3>${side}`, "pu");
            return
        }
        if ((b = t.closest(".cs .cb"))) {
            const c = b.parentElement, o = c.classList.contains("open");
            $$(".cs.open").forEach(x => x.classList.remove("open"));
            if (!o) c.classList.add("open");
            return
        }
        if ((b = t.closest(".cs .co"))) {
            const c = b.closest(".cs"), i = $("input", c);
            i.value = b.dataset.v;
            $(".cb span", c).textContent = b.textContent;
            $$(".co", c).forEach(x => x.classList.toggle("on", x === b));
            c.classList.remove("open");
            if (c.dataset.nav) {
                const u = new URL(location.href);
                b.dataset.v ? u.searchParams.set(c.dataset.nav, b.dataset.v) : u.searchParams.delete(c.dataset.nav);
                u.searchParams.delete("page");
                location.href = u
            } else if (c.dataset.ps) {
                const u = new URL(location.href);
                u.searchParams.set("ps", b.dataset.v);
                u.searchParams.delete("page");
                location.href = u
            }
            applyWhen();
            if (c.dataset.aud !== undefined) audRefresh();
            return
        }
        if (!t.closest(".cs")) $$(".cs.open").forEach(x => x.classList.remove("open"));
        if ((b = t.closest("[data-seg] button"))) {
            const w = b.parentElement;
            $("input", w).value = b.dataset.v;
            $$("button", w).forEach(x => x.classList.toggle("on", x === b));
            applyWhen();
            if (w.dataset.pref) {
                PREF[w.dataset.pref] = b.dataset.v;
                if (w.dataset.pref === "theme") {
                    const d = document.documentElement;
                    d.dataset.theme = b.dataset.v;
                    try {
                        localStorage.setItem("km-theme", b.dataset.v)
                    } catch (_) {
                    }
                }
                savePref();
                toast("Sozlama saqlandi")
            }
            if (w.dataset.aud !== undefined) audRefresh();
            return
        }
        if ((b = t.closest("[data-mode]"))) {
            document.cookie = "km_mode=" + b.dataset.mode + ";path=/;max-age=31536000;samesite=lax"
        }
        if ((b = t.closest("[data-rail-reset]"))) {
            try {
                localStorage.removeItem("km-rail")
            } catch (_) {
            }
            toast("Panel joyi asl holatga qaytdi");
            return
        }
        if ((b = t.closest("[data-proxy]"))) {
            const x = $(".atb").children[+b.dataset.proxy];
            x && x.click();
            return
        }
        if ((b = t.closest("[data-toast]"))) {
            toast(b.dataset.toast, "x");
            return
        }
        if ((b = t.closest("[data-href]")) && !t.closest("a,button,form,input,label,.ib2,.cs")) {
            location.href = b.dataset.href;
            return
        }
        if ((b = t.closest("[data-cmd]"))) {
            document.execCommand(b.dataset.cmd);
            return
        }
        if ((b = t.closest("[data-ins]"))) {
            document.execCommand("insertText", false, b.dataset.ins);
            return
        }
        if ((b = t.closest("[data-fm]"))) {
            const w = b.closest(".edw"), i = $(".fi", w), s = i.value.trim();
            if (!s) return;
            const ed = $(".ed", w), g = getSelection();
            ed.focus();
            if (lastRange && ed.contains(lastRange.commonAncestorContainer)) {
                g.removeAllRanges();
                g.addRange(lastRange)
            } else {
                const n = document.createRange();
                n.selectNodeContents(ed);
                n.collapse(false);
                g.removeAllRanges();
                g.addRange(n)
            }
            document.execCommand("insertHTML", false, FORM(s.replace(/[<>&]/g, c => ({
                "<": "&lt;",
                ">": "&gt;",
                "&": "&amp;"
            }[c]))) + "&nbsp;");
            i.value = "";
            return
        }
        if ((b = t.closest("[data-addq]"))) {
            addQ();
            return
        }
        if ((b = t.closest("[data-delq]"))) {
            const q = b.closest(".qb");
            ask("Savol o‘chirilsinmi?", () => q.remove());
            return
        }
        if ((b = t.closest("[data-addv]"))) {
            addV(b.closest(".qb"));
            return
        }
        if ((b = t.closest("[data-delv]"))) {
            const q = b.closest(".qb");
            if ($$(".vr", q).length <= 2) return toast("Kamida 2 ta variant bo‘lishi kerak", "x");
            const r = b.closest(".vr");
            ask("Variant o‘chirilsinmi?", () => {
                r.remove();
                if (!$("input:checked", q)) $(".vr input", q).checked = true
            });
            return
        }
        if ((b = t.closest("[data-key]"))) {
            const r = b.closest(".kr");
            r.dataset.a = b.dataset.key;
            $$(".kbt", r).forEach((x, i) => x.classList.toggle("on", i == b.dataset.key));
            return
        }
        if ((b = t.closest("[data-keysol]"))) {
            const s = $(".ks", b.closest(".kr"));
            s.style.display = s.style.display === "none" ? "" : "none";
            return
        }
        if ((b = t.closest("[data-keydel]"))) {
            const r = b.closest(".kr");
            ask("Savol o‘chirilsinmi?", () => r.remove());
            return
        }
        if ((b = t.closest("[data-keygen]"))) {
            const n = Math.min(200, Math.max(1, +$("#kn").value || 20)),
                k = Math.min(8, Math.max(2, +$("#ko").value || 4));
            const go = () => keyBuild(n, k);
            $("#kg").children.length ? ask("Mavjud kalitlar o‘chib, yangi varaqa yaratiladi. Davom etilsinmi?", go) : go();
            return
        }
        if ((b = t.closest("[data-keyadd]"))) {
            const g = $("#kg");
            g.insertAdjacentHTML("beforeend", KROW(+g.dataset.k || 4, -1, "", false));
            fx(g);
            return
        }
        if ((b = t.closest("[data-keyfill]"))) {
            const txt = $("#kq").value.toUpperCase(), rows = $$("#kg .kr"), k = +$("#kg").dataset.k || 4;
            if (!rows.length) return toast("Avval kalit varaqasini yarating", "x");
            let c = 0;
            const set = (r, j) => {
                r.dataset.a = j;
                $$(".kbt", r).forEach((x, i) => x.classList.toggle("on", i === j));
                c++
            };
            const m = [...txt.matchAll(/(\d+)\s*[-.:)]?\s*([A-H])/g)];
            if (m.length) m.forEach(x => {
                const i = +x[1] - 1, j = "ABCDEFGH".indexOf(x[2]);
                if (rows[i] && j < k) set(rows[i], j)
            }); else [...txt.replace(/[^A-H]/g, "")].forEach((ch, i) => {
                const j = "ABCDEFGH".indexOf(ch);
                if (rows[i] && j < k) set(rows[i], j)
            });
            toast(c + " ta kalit qo‘llandi");
            return
        }
        if ((b = t.closest("[data-add-module]"))) {
            const tp = $("#mod-tpl"), box = $("#mods");
            box.insertAdjacentHTML("beforeend", tp.innerHTML.replace(/__N__/g, box.children.length + 1));
            fx(box);
            return
        }
        if ((b = t.closest("[data-gift-user]"))) {
            giftFromUser(+b.dataset.giftUser);
            return
        }
        if ((b = t.closest("[data-gift-course]"))) {
            giftFromCourse(+b.dataset.giftCourse);
            return
        }
        if ((b = t.closest("[data-picker]"))) {
            const d = b.dataset;
            pick({
                title: d.title,
                items: jsonData(d.src),
                multi: d.multi === "1",
                all: d.multi === "1",
                btn: d.btn || "Qo‘shish",
                cb: async ids => {
                    try {
                        await pj(d.url, {[d.key]: d.multi === "1" ? ids : ids[0]});
                        toast("Saqlandi");
                        setTimeout(() => location.reload(), 500)
                    } catch (er) {
                        toast(er.message, "x")
                    }
                }
            });
            return
        }
        if ((b = t.closest("[data-pick-into]"))) {
            pickInto(b);
            return
        }
        if ((b = t.closest("[data-fview]"))) {
            ov(`<div class="row" style="margin-bottom:10px;flex-wrap:nowrap"><h3 class="sp">${esc(b.dataset.name)}</h3><button class="bt s" data-close>Yopish</button></div><div class="pvh" data-kind="${b.dataset.kind}" data-pk="${b.dataset.pk}"></div>${ROLE === "student" ? `<p class="m mt">Faylni yuklab olish yoki nusxalash taqiqlangan. Har bir sahifada sizning ID raqamingiz ko‘rinib turadi.</p>` : ""}`, "ct wd xl");
            return
        }
        if ((b = t.closest("[data-report]"))) {
            const url = b.dataset.report, q = b.dataset.q;
            ov(`<h3 style="margin-bottom:6px">Test xatoligi haqida xabar</h3><p class="m" style="margin-bottom:10px">${+q + 1}-savol</p><div data-editor="Xatolikni batafsil yozing…" id="rep-ed"></div><div class="row mt"><button class="bt s" data-close>Bekor qilish</button><div class="sp"></div><button class="bt" id="rep-send">${I("send")} Yuborish</button></div>`, "ct wd");
            edInit($("#ov"));
            $("#rep-send").onclick = async () => {
                const h = $("#ov .ed").innerHTML.trim();
                if (!h) return toast("Xatolik haqida yozing", "x");
                const fd = new FormData();
                fd.append("html", h);
                fd.append("q", q);
                const r = await fetch(url, {
                    method: "POST",
                    body: fd,
                    credentials: "same-origin",
                    headers: {"X-CSRFToken": csrf(), "X-Requested-With": "fetch"}
                });
                closeOv();
                toast(r.ok ? "Xabaringiz adminga yuborildi" : "Yuborib bo‘lmadi", r.ok ? "" : "x")
            };
            return
        }
        if ((b = t.closest("[data-copy]"))) {
            copy($(b.dataset.copy).value).then(ok => toast(ok ? "Nusxalandi" : "Nusxalab bo‘lmadi", ok ? "" : "x"));
            return
        }
        if ((b = t.closest("[data-regen]"))) {
            const s = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*?", a = new Uint32Array(12);
            crypto.getRandomValues(a);
            $(b.dataset.regen).value = [...a].map(x => s[x % s.length]).join("");
            toast("Yangi parol yaratildi");
            return
        }
        if ((b = t.closest("[data-copy-text]"))) {
            copy(b.dataset.copyText).then(ok => toast(ok ? "Nusxalandi" : "Nusxalab bo‘lmadi", ok ? "" : "x"));
            return
        }
        if ((b = t.closest("[data-perm]"))) {
            return
        }
        if ((b = t.closest("[data-pw-eye]"))) {
            const i = $(b.dataset.pwEye);
            if (i) {
                i.type = i.type === "password" ? "text" : "password";
                b.innerHTML = I(i.type === "password" ? "eye" : "eye-off");
                fx(b)
            }
            return
        }
    });
    document.addEventListener("change", e => {
        const t = e.target;
        if (t.matches("[data-perm-toggle]")) pj(t.dataset.permToggle, {
            code: t.dataset.code,
            on: t.checked ? 1 : 0
        }).then(() => toast(t.checked ? "Ruxsat berildi" : "Ruxsat olib tashlandi")).catch(er => {
            toast(er.message, "x");
            t.checked = !t.checked
        });
        if (t.matches("[data-edimg]")) {
            const f = t.files[0];
            if (!f) return;
            const fd = new FormData();
            fd.append("file", f);
            fetch("/editor/upload/", {
                method: "POST",
                body: fd,
                credentials: "same-origin",
                headers: {"X-CSRFToken": csrf(), "X-Requested-With": "fetch"}
            }).then(r => r.json()).then(j => {
                if (!j.ok) return toast(j.error, "x");
                $(".ed", t.closest(".edw")).insertAdjacentHTML("beforeend", `<img src="${j.url}" alt="">`)
            });
            t.value = ""
        }
        if (t.matches("[data-autosubmit]")) t.form.submit();
        if (t.name === "mode" || t.matches("[data-autouser]")) {
        }
    });
    document.addEventListener("input", e => {
        const t = e.target;
        if (t.matches("[data-search]")) {
            clearTimeout(K.st);
            K.st = setTimeout(() => {
                const u = new URL(location.href);
                t.value ? u.searchParams.set("q", t.value) : u.searchParams.delete("q");
                u.searchParams.delete("page");
                location.href = u
            }, 450)
        }
        if (t.matches("[data-autouser]")) {
            const un = $(t.dataset.autouser);
            if (un && !un.dataset.man) {
                const m = {
                    а: "a",
                    б: "b",
                    в: "v",
                    г: "g",
                    д: "d",
                    е: "e",
                    ж: "j",
                    з: "z",
                    и: "i",
                    й: "y",
                    к: "k",
                    л: "l",
                    м: "m",
                    н: "n",
                    о: "o",
                    п: "p",
                    р: "r",
                    с: "s",
                    т: "t",
                    у: "u",
                    ф: "f",
                    х: "x",
                    ц: "ts",
                    ч: "ch",
                    ш: "sh",
                    ы: "i",
                    э: "e",
                    ю: "yu",
                    я: "ya",
                    ў: "o",
                    қ: "q",
                    ғ: "g",
                    ҳ: "h"
                };
                un.value = t.value.toLowerCase().split("").map(c => m[c] ?? c).join("").replace(/[‘’ʻ'`]/g, "").replace(/[^a-z0-9]+/g, ".").replace(/^\.+|\.+$/g, "")
            }
        }
        if (t.matches("[data-manual]")) t.dataset.man = 1;
    });
    document.addEventListener("submit", e => {
        const f = e.target;
        if (f.matches("[data-confirm-submit]") && !f.dataset.ok) {
            e.preventDefault();
            ask(f.dataset.confirmSubmit, () => {
                f.dataset.ok = 1;
                f.requestSubmit ? f.requestSubmit() : f.submit()
            })
        }
        const lf = f.querySelector("[name=tz]");
        if (lf) {
            try {
                lf.value = Intl.DateTimeFormat().resolvedOptions().timeZone;
                f.querySelector("[name=lang]").value = navigator.language;
                f.querySelector("[name=scr]").value = screen.width + "×" + screen.height
            } catch (_) {
            }
        }
    });

    /* ---------- boshlanish ---------- */
    function flash() {
        const e = $("#flash");
        if (!e) return;
        try {
            JSON.parse(e.textContent).forEach((m, i) => setTimeout(() => toast(m.t, m.l === "error" ? "x" : ""), i * 350))
        } catch (_) {
        }
    }

    function countdown() {
        $$("[data-until]").forEach(el => {
            const at = new Date(el.dataset.until).getTime(), cd = el.querySelector("[data-cd]");
            const tick = () => {
                const ms = at - Date.now();
                if (ms <= 0) {
                    const k = "rl" + el.dataset.until;
                    if (!sessionStorage.getItem(k)) {
                        sessionStorage.setItem(k, 1);
                        setTimeout(() => location.reload(), 800)
                    }
                    return
                }
                const m = Math.floor(ms / 6e4), d = Math.floor(m / 1440), h = Math.floor(m % 1440 / 60);
                if (cd) cd.textContent = (d ? d + " kun " : "") + (h ? h + " soat " : "") + (m % 60) + " daqiqa " + Math.floor(ms % 6e4 / 1e3) + " soniya"
            };
            tick();
            setInterval(tick, 1000)
        });
    }

    function init() {
        fx();
        edInit();
        testInit();
        applyWhen();
        flash();
        countdown();
        rail();
        connect();
        audRefresh();
        const s = $("[data-search]");
        if (s && s.value) {
            s.focus();
            s.setSelectionRange(s.value.length, s.value.length)
        }
        const u = new URL(location.href);
        if (u.searchParams.get("gift")) {
            const g = $("[data-gift-user]");
            g && g.click()
        }
        $$("[data-seg][data-pref] button").forEach(b => {
            const w = b.parentElement, k = w.dataset.pref;
            if (k === "mode" || k === "act") {
                const v = PREF[k];
                $("input", w).value = v;
                b.classList.toggle("on", b.dataset.v === v)
            }
        });
    }

    document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
