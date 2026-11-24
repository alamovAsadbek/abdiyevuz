/* Meeting xonasi: WebRTC (mesh) + WebSocket signaling, chat, @belgilash, moderatsiya.
   Barcha ruxsatlar serverda tekshiriladi — bu yerdagi tugmalar faqat qulaylik uchun. */
(() => {
  "use strict";
  const R = document.getElementById("room");
  if (!R) return;
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const KM = window.KM, toast = KM.toast, fx = KM.fx;
  const PK = R.dataset.pk, ME = +R.dataset.me;
  const ICE = JSON.parse($("#ice").textContent || "[]");
  const el = (t, c, txt) => { const e = document.createElement(t); if (c) e.className = c; if (txt != null) e.textContent = txt; return e };
  const ic = n => { const i = document.createElement("i"); i.setAttribute("data-feather", n); return i };
  const secure = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

  let ws = null, joined = false, ended = false, retry = 0, me = null, roster = new Map(), perms = {}, caps = { mic: true, cam: true, chat: true, screen: false };
  let chatOn = true, mentionables = [], unread = 0, startAt = null;
  const peers = new Map();           // uid -> {pc, ms, polite, making, ignore, tx:{audio,video}}
  const tracks = { audio: null, cam: null, screen: null };
  const state = { mic: false, cam: false, screen: false, hand: false };
  const want = { mic: false, cam: false };   // lobbydagi tanlov
  let pinned = null, activeUid = null, mode = "speaker", defaults = { mic: true, cam: true, screen: false }, recOn = false;

  /* ------------------------------------------------------------------ lobby */
  let prevStream = null;
  async function lobbyMedia() {
    try {
      if (prevStream) prevStream.getTracks().forEach(t => t.stop()); prevStream = null;
      const a = want.mic, v = want.cam;
      if (a || v) prevStream = await navigator.mediaDevices.getUserMedia({ audio: a, video: v ? VID : false });
      $("#prev").srcObject = prevStream && v ? prevStream : null;
      $("#noprev").hidden = !!(prevStream && v);
    } catch (e) { toast("Qurilmaga ruxsat berilmadi: " + (e.name || e.message), "x"); return false }
    return true;
  }
  const VID = { width: { ideal: 640 }, height: { ideal: 360 }, frameRate: { ideal: 24, max: 30 } };
  function setBtn(b, on, icOn, icOff) {
    b.dataset.on = on ? "1" : "0"; b.classList.toggle("on", on); b.replaceChildren(ic(on ? icOn : icOff)); fx();
  }
  if (!secure) $("#lb-note").textContent = "Brauzer kamera/mikrofonga ruxsat bermayapti (sayt HTTPS orqali ochilishi kerak). Siz baribir tinglash va yozish orqali qatnasha olasiz.";
  $("#lb-mic").onclick = async () => { if (!secure) return toast("Kamera/mikrofon uchun HTTPS kerak", "x"); want.mic = !want.mic; if (!(await lobbyMedia())) want.mic = false; setBtn($("#lb-mic"), want.mic, "mic", "mic-off") };
  $("#lb-cam").onclick = async () => { if (!secure) return toast("Kamera/mikrofon uchun HTTPS kerak", "x"); want.cam = !want.cam; if (!(await lobbyMedia())) want.cam = false; setBtn($("#lb-cam"), want.cam, "video", "video-off") };
  $("#join").onclick = () => {
    if (prevStream) { prevStream.getTracks().forEach(t => t.stop()); prevStream = null }
    ensureCtx(); $("#lobby").hidden = true; $("#mr-app").hidden = false; connect();
  };

  /* ------------------------------------------------------------------ websocket */
  const send = o => { try { ws && ws.readyState === 1 && ws.send(JSON.stringify(o)) } catch (_) {} };
  function connect() {
    ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + `/ws/meeting/${PK}/`);
    ws.onopen = () => { retry = 0 };
    ws.onmessage = ev => { let d; try { d = JSON.parse(ev.data) } catch (_) { return } handle(d) };
    ws.onclose = ev => {
      if (ended) return;
      if (ev.code >= 4400 && ev.code < 4500) return;       // denied / replaced / kicked — o'zimiz hal qilganmiz
      if (ev.code === 4000) return;
      closeAllPeers();
      if (retry++ < 8) { toast("Aloqa uzildi, qayta ulanmoqda…", "x"); setTimeout(connect, Math.min(8000, 800 * retry)) }
      else over("Aloqa uzildi", "Internetni tekshirib, sahifani qayta yuklang.");
    };
  }
  setInterval(() => send({ type: "ping" }), 25000);

  function over(t, p) {
    ended = true; closeAllPeers(); stopAllLocal(); try { ws && ws.close() } catch (_) {}
    $("#over-t").textContent = t; $("#over-p").textContent = p || ""; $("#over").hidden = false;
  }

  function handle(d) {
    switch (d.type) {
      case "init": return onInit(d);
      case "denied": return over("Kirib bo‘lmadi", d.reason);
      case "replaced": return over("Boshqa oynada ochildi", "Siz bu meetingga boshqa oyna/qurilmadan qo‘shildingiz.");
      case "kicked": return over("Siz meetingdan chiqarildingiz", "Boshlovchi sizni meetingdan chiqarib yubordi.");
      case "ended": return over("Meeting yakunlandi", d.auto ? "Hech kim qolmagani uchun avtomatik yakunlandi." : "Boshlovchi meetingni yakunladi.");
      case "peer_joined": return onJoined(d.peer);
      case "peer_left": return onLeft(d);
      case "signal": return onSignal(d);
      case "recording": setRec(d.on); if (!d.on && rec) stopRec(true); return;
      case "defaults": defaults = d.d; paintBar(); toast(d.d.mic && d.d.cam ? "Hammaga gapirishga ruxsat berildi" : "Umumiy gapirish ruxsati olib qo‘yildi"); return;
      case "state": { const r = roster.get(d.uid); if (r) { if (d.state.hand && !(r.state || {}).hand && d.uid !== ME && me && me.role !== "member") { toast(`${r.name} qo‘l ko‘tardi`); } r.state = d.state; renderTile(d.uid); renderPeople() } if (d.uid === ME) syncLocalFromServer(d.state); return }
      case "chat": return addMsg(d.c);
      case "comment_deleted": return delMsg(d.id);
      case "notice": return toast(d.text, "x");
      case "denied_media": return d.what.forEach(k => { toast(`Sizda ${({ mic: "mikrofon", cam: "kamera", screen: "ekran" })[k]} ruxsati yo‘q`, "x"); stopKind(k === "mic" ? "mic" : k, true) });
      case "force": return stopKind(d.what, true, true);
      case "caps": { const had = caps.mic || caps.cam; caps = d.caps; applyCaps(); if (!had && (caps.mic || caps.cam)) toast("Sizga gapirishga ruxsat berildi — mikrofon/kamerani yoqishingiz mumkin"); return }
      case "caps_of": { const r = roster.get(d.uid); if (r) { r.caps = d.caps; r.state = d.state; renderPeople(); renderTile(d.uid) } return }
      case "chat_toggle": chatOn = d.on; applyCaps(); toast(d.on ? "Chat yoqildi" : "Chat o‘chirildi"); return;
      case "refresh_caps": location.reload(); return;
    }
  }

  function onInit(d) {
    me = d.me; perms = d.perms; caps = d.me.caps; defaults = d.defaults || defaults; setRec(!!d.recording); chatOn = d.meeting.chat_on; mentionables = d.mentionables;
    startAt = d.meeting.started ? new Date(d.meeting.started) : new Date();
    roster = new Map(d.roster.map(r => [r.uid, r])); roster.set(ME, d.me); d.me.online = true;
    d.peers.forEach(p => { p.online = true; roster.set(p.uid, p) });
    $("#msgs").replaceChildren(); d.comments.forEach(c => addMsg(c, true)); scroll();
    closeAllPeers(); $("#grid").replaceChildren(); roster.forEach((r, uid) => { if (r.online) renderTile(uid) });
    d.peers.forEach(p => { newPeer(p.uid, true) });
    applyCaps(); renderPeople();
    // lobbyda tanlangan qurilmalar
    if (want.mic) toggle("mic", true); if (want.cam) toggle("cam", true);
  }
  function onJoined(p) {
    p.online = true; roster.set(p.uid, p); closePeer(p.uid); newPeer(p.uid, false);   // yangi qatnashchi o'zi offer yuboradi
    renderTile(p.uid); renderPeople(); toast(`${p.name} qo‘shildi`);
  }
  function onLeft(d) {
    const r = roster.get(d.uid);
    if (r) { r.online = false; r.state = {}; }
    closePeer(d.uid); const t = $(`#tile-${d.uid}`); if (t) t.remove(); unwatch(d.uid); if (pinned === d.uid) pinned = null; if (activeUid === d.uid) activeUid = null; layout(); renderPeople();
    if (r) toast(d.kicked ? `${r.name} chiqarib yuborildi` : `${r.name} chiqib ketdi`);
    if (d.kicked && r) roster.delete(d.uid);
  }

  /* ------------------------------------------------------------------ WebRTC (perfect negotiation) */
  const cur = kind => kind === "audio" ? tracks.audio : (tracks.screen || tracks.cam);
  function newPeer(uid, offerer) {
    const pc = new RTCPeerConnection({ iceServers: ICE });
    const P = { pc, ms: new MediaStream(), polite: ME > uid, making: false, ignore: false, tx: {} };
    peers.set(uid, P);
    pc.ontrack = e => { P.ms.addTrack(e.track); if (e.track.kind === "audio") watchAudio(uid, e.track); const v = $(`#tile-${uid} video`); if (v && v.srcObject !== P.ms) v.srcObject = P.ms; v && v.play && v.play().catch(() => {}) };
    pc.onicecandidate = e => { if (e.candidate) send({ type: "signal", to: uid, data: { c: e.candidate } }) };
    pc.onnegotiationneeded = async () => {
      try { P.making = true; await pc.setLocalDescription(); send({ type: "signal", to: uid, data: { d: pc.localDescription } }) }
      catch (_) {} finally { P.making = false }
    };
    pc.oniceconnectionstatechange = () => { if (pc.iceConnectionState === "failed") try { pc.restartIce() } catch (_) {} };
    if (offerer) { P.tx.audio = pc.addTransceiver("audio", { direction: "sendrecv" }); P.tx.video = pc.addTransceiver("video", { direction: "sendrecv" }); attach(P) }
    return P;
  }
  function attach(P) {
    ["audio", "video"].forEach(k => {
      const t = P.tx[k]; if (!t) return;
      try { t.direction = "sendrecv"; t.sender.replaceTrack(cur(k)).catch(() => {}) } catch (_) {}
    });
    tune(P);
  }
  function tune(P) {   // tarmoq tejash: mesh uchun video bitrate cheklovi
    const s = P.tx.video && P.tx.video.sender; if (!s || !s.getParameters) return;
    try { const p = s.getParameters(); if (!p.encodings || !p.encodings.length) p.encodings = [{}]; p.encodings[0].maxBitrate = tracks.screen ? 1500000 : 700000; s.setParameters(p).catch(() => {}) } catch (_) {}
  }
  async function onSignal(m) {
    let P = peers.get(m.from);
    if (!P) { if (!(m.data && m.data.d)) return; P = newPeer(m.from, false) }
    const { pc } = P, d = m.data;
    try {
      if (d.d) {
        const collision = d.d.type === "offer" && (P.making || pc.signalingState !== "stable");
        P.ignore = !P.polite && collision; if (P.ignore) return;
        await pc.setRemoteDescription(d.d);
        if (d.d.type === "offer") {
          pc.getTransceivers().forEach(t => { const k = t.receiver.track.kind; if (!P.tx[k]) P.tx[k] = t });
          attach(P);
          await pc.setLocalDescription(); send({ type: "signal", to: m.from, data: { d: pc.localDescription } });
        }
      } else if (d.c) { try { await pc.addIceCandidate(d.c) } catch (e) { if (!P.ignore) throw e } }
    } catch (e) { console.warn("signal", e) }
  }
  function closePeer(uid) { const P = peers.get(uid); if (!P) return; try { P.pc.close() } catch (_) {} peers.delete(uid) }
  function closeAllPeers() { [...peers.keys()].forEach(closePeer) }

  /* ------------------------------------------------------------------ mahalliy media */
  function pushTracks() { peers.forEach(P => { ["audio", "video"].forEach(k => { const t = P.tx[k]; if (t) t.sender.replaceTrack(cur(k)).catch(() => {}) }); tune(P) }) }
  function stopTrack(k) { if (tracks[k]) { tracks[k].onended = null; tracks[k].stop(); tracks[k] = null } }
  function stopAllLocal() { ["audio", "cam", "screen"].forEach(stopTrack) }
  function stopKind(k, report, forced) {
    if (k === "mic") { stopTrack("audio"); unwatch(ME); state.mic = false }
    else if (k === "cam") { stopTrack("cam"); state.cam = false }
    else if (k === "screen") { stopTrack("screen"); state.screen = false }
    pushTracks(); paintBar(); renderTile(ME);
    if (report) send({ type: "state", [k]: false });
    if (forced) toast({ mic: "Mikrofoningiz o‘chirildi", cam: "Kamerangiz o‘chirildi", screen: "Ekran ulashishingiz to‘xtatildi" }[k] || "O‘chirildi", "x");
  }
  async function toggle(k, force) {
    const on = force != null ? force : !state[k];
    if (!on) return stopKind(k, true);
    if (!caps[k]) return toast("Sizga bu imkoniyat berilmagan", "x");
    if (!secure) return toast("Kamera/mikrofon uchun sayt HTTPS orqali ochilishi kerak", "x");
    try {
      if (k === "mic") { const s = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } }); tracks.audio = s.getAudioTracks()[0]; watchAudio(ME, tracks.audio); tracks.audio.onended = () => stopKind("mic", true) }
      if (k === "cam") { const s = await navigator.mediaDevices.getUserMedia({ video: VID }); tracks.cam = s.getVideoTracks()[0]; tracks.cam.onended = () => stopKind("cam", true) }
      if (k === "screen") { const s = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 15, max: 24 } } }); tracks.screen = s.getVideoTracks()[0]; tracks.screen.onended = () => stopKind("screen", true) }
    } catch (e) { toast("Ruxsat berilmadi: " + (e.name || "xato"), "x"); if (k === "mic") want.mic = false; return }
    state[k] = true; pushTracks(); paintBar(); renderTile(ME); send({ type: "state", [k]: true });
  }
  function syncLocalFromServer(s) { state.hand = !!s.hand; paintBar() }   // mic/cam/ekranni server "force" hodisasi o‘chiradi

  /* ------------------------------------------------------------------ pastki panel */
  function paintBar() {
    const mk = (id, on, a, b, can) => { const x = $(id); x.classList.toggle("on", on); x.disabled = !can; x.classList.toggle("off", !can); x.replaceChildren(ic(on ? a : b)) };
    mk("#b-mic", state.mic, "mic", "mic-off", caps.mic); mk("#b-cam", state.cam, "video", "video-off", caps.cam);
    mk("#b-scr", state.screen, "monitor", "monitor", caps.screen); mk("#b-hand", state.hand, "hand", "hand", true);
    $("#b-muteall").hidden = !perms.mute; $("#b-allow").hidden = !perms.grant; $("#b-allow").classList.toggle("on", !!(defaults.mic && defaults.cam)); $("#b-rec").hidden = !perms.rec; $("#b-chat").hidden = !perms.grant; $("#b-end").hidden = !perms.end; $("#b-chat").classList.toggle("on", !chatOn);
    fx();
  }
  function applyCaps() {
    ["mic", "cam", "screen"].forEach(k => { if (!caps[k] && state[k]) stopKind(k, true) });
    const inp = $("#ctext"); inp.disabled = !(chatOn && caps.chat);
    inp.placeholder = chatOn && caps.chat ? "Xabar yozing… @ bilan belgilang" : (chatOn ? "Sizga yozish ruxsati berilmagan" : "Chat o‘chirilgan");
    paintBar();
  }
  $("#b-mic").onclick = () => toggle("mic"); $("#b-cam").onclick = () => toggle("cam"); $("#b-scr").onclick = () => toggle("screen");
  $("#b-hand").onclick = () => { state.hand = !state.hand; send({ type: "state", hand: state.hand }); paintBar() };
  $("#b-muteall").onclick = () => send({ type: "mute_all" });
  $("#b-chat").onclick = () => send({ type: "chat_toggle", on: !chatOn });
  $("#b-leave").onclick = () => {
    const go = () => { ended = true; try { ws.close() } catch (_) {} closeAllPeers(); stopAllLocal(); location.href = R.dataset.bk };
    if (rec) { rec.after = go; stopRec(); setTimeout(go, 9000) } else go();
  };
  $("#b-end").onclick = () => KM.ask("Meeting hamma uchun yakunlansinmi?", () => { if (rec) { rec.after = () => send({ type: "end" }); stopRec(); setTimeout(() => send({ type: "end" }), 9000) } else send({ type: "end" }) });
  addEventListener("beforeunload", () => { try { ws && ws.close() } catch (_) {} });
  setInterval(() => { if (startAt) { const s = Math.max(0, Math.floor((Date.now() - startAt) / 1000)); $("#mr-clock").textContent = [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((x, i) => i ? String(x).padStart(2, "0") : x).join(":") } }, 1000);

  /* ------------------------------------------------------------------ video plitkalar */
  function pickBig() {
    const ids = [...$("#grid").children].map(t => +t.id.slice(5));
    if (pinned && ids.includes(pinned)) return pinned;
    const sc = ids.find(u => (u === ME ? state.screen : (roster.get(u) && (roster.get(u).state || {}).screen)));
    if (sc) return sc;
    if (activeUid && ids.includes(activeUid)) return activeUid;
    const host = ids.find(u => u !== ME && roster.get(u) && roster.get(u).role === "host");
    return host || ids.find(u => u !== ME) || ME;
  }
  function layout() {
    const g = $("#grid"), tiles = [...g.children], n = tiles.length, big = pickBig();
    g.dataset.cols = Math.min(n, 9); g.dataset.mode = mode; g.dataset.alone = n < 2 ? "1" : "0";
    g.style.setProperty("--span", Math.max(1, n - 1));
    tiles.forEach(t => { const u = +t.id.slice(5); t.classList.toggle("big", mode === "speaker" && u === big); const pin = $(".mr-pin", t); if (pin) pin.hidden = pinned !== u });
  }
  $("#b-view").onclick = () => { mode = mode === "speaker" ? "grid" : "speaker"; pinned = null; layout(); toast(mode === "speaker" ? "Katta oyna: gapirayotgan odam" : "Hammasi bir xil o‘lchamda") };

  /* ----- gapirayotgan odamni aniqlash (ovoz balandligi) ----- */
  let actx = null, recDest = null; const an = new Map();
  function ensureCtx() { const C = window.AudioContext || window.webkitAudioContext; if (!actx && C) actx = new C(); if (actx && actx.state === "suspended") actx.resume().catch(() => {}); return actx }
  function unwatch(uid) { const a = an.get(uid); if (a) { try { a.src.disconnect() } catch (_) {} an.delete(uid) } }
  function watchAudio(uid, track) {
    const c = ensureCtx(); if (!c || !track) return; unwatch(uid);
    const src = c.createMediaStreamSource(new MediaStream([track])), node = c.createAnalyser(); node.fftSize = 512; src.connect(node);
    if (recDest) src.connect(recDest);
    an.set(uid, { src, node, buf: new Uint8Array(node.fftSize), hits: 0 });
  }
  setInterval(() => {
    let best = null, lvl = 0;
    an.forEach((a, uid) => {
      a.node.getByteTimeDomainData(a.buf); let m = 0; for (const v of a.buf) { const d = Math.abs(v - 128); if (d > m) m = d }
      const on = uid === ME ? state.mic : !!(roster.get(uid) && (roster.get(uid).state || {}).mic), sp = on && m > 10;
      a.hits = sp ? a.hits + 1 : 0; const t = $(`#tile-${uid}`); t && t.classList.toggle("speaking", sp);
      if (uid !== ME && a.hits >= 2 && m > lvl) { best = uid; lvl = m }
    });
    if (best && best !== activeUid) { activeUid = best; layout() }
  }, 200);

  /* ----- yozib olish (faqat egasi/asosiy o'qituvchi): sahna + hamma ovozi -> server ----- */
  let rec = null;
  const csrf = () => $('meta[name=csrf]').content;
  const post = (u, body) => fetch(u, { method: "POST", body, credentials: "same-origin", headers: { "X-CSRFToken": csrf(), "X-Requested-With": "fetch" } });
  function setRec(on) { recOn = on; $("#mr-rec").hidden = !on; const b = $("#b-rec"); b.classList.toggle("dg", on); b.title = on ? "Yozishni to‘xtatish" : "Yozib olish"; b.replaceChildren(ic(on ? "square" : "circle")); fx(); if (on) toast("Meeting yozib olinmoqda") }
  function drawTile(g, uid, x, y, w, h) {
    const t = $(`#tile-${uid}`); if (!t) return; const v = $("video", t), r = roster.get(uid) || {};
    g.fillStyle = "#1d1a33"; g.fillRect(x + 2, y + 2, w - 4, h - 4);
    if (!t.classList.contains("novid") && v.videoWidth) { const k = Math.min((w - 4) / v.videoWidth, (h - 4) / v.videoHeight), dw = v.videoWidth * k, dh = v.videoHeight * k; g.drawImage(v, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh) }
    else { g.fillStyle = "#6b5bd2"; g.beginPath(); g.arc(x + w / 2, y + h / 2, Math.min(w, h) / 5, 0, 7); g.fill(); g.fillStyle = "#fff"; g.font = `700 ${Math.min(w, h) / 6}px sans-serif`; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(r.ini || "?", x + w / 2, y + h / 2) }
    g.fillStyle = "rgba(0,0,0,.55)"; g.fillRect(x + 8, y + h - 30, Math.min(w - 16, 220), 22); g.fillStyle = "#fff"; g.font = "13px sans-serif"; g.textAlign = "left"; g.textBaseline = "middle"; g.fillText(r.name || "", x + 14, y + h - 19);
  }
  function drawFrame() {
    if (!rec) return; const g = rec.canvas.getContext("2d"); g.fillStyle = "#0f0d1a"; g.fillRect(0, 0, 1280, 720);
    const ids = [...$("#grid").children].map(t => +t.id.slice(5)), big = pickBig(), others = ids.filter(u => u !== big);
    drawTile(g, big, 0, 0, others.length ? 1040 : 1280, 720); others.slice(0, 4).forEach((u, i) => drawTile(g, u, 1040, i * 180, 240, 180));
  }
  async function startRec() {
    const c = ensureCtx(); if (!c || !window.MediaRecorder) return toast("Brauzer yozib olishni qo‘llamaydi", "x");
    const r = await post(`/meetings/${PK}/rec/start/`).then(x => x.json()).catch(() => ({}));
    if (!r.ok) return toast(r.error || "Yozishni boshlab bo‘lmadi", "x");
    recDest = c.createMediaStreamDestination(); an.forEach(a => { try { a.src.connect(recDest) } catch (_) {} });
    const canvas = document.createElement("canvas"); canvas.width = 1280; canvas.height = 720;
    const stream = canvas.captureStream(15); recDest.stream.getAudioTracks().forEach(t => stream.addTrack(t));
    const mt = ["video/webm;codecs=vp8,opus", "video/webm"].find(x => MediaRecorder.isTypeSupported(x));
    const mr = new MediaRecorder(stream, { mimeType: mt, videoBitsPerSecond: 1500000, audioBitsPerSecond: 96000 });
    const wk = new Worker(URL.createObjectURL(new Blob(["setInterval(()=>postMessage(1),66)"], { type: "text/javascript" })));
    rec = { id: r.id, mr, canvas, wk, q: Promise.resolve(), done: false };
    wk.onmessage = drawFrame;
    mr.ondataavailable = e => { if (e.data && e.data.size) rec.q = rec.q.then(() => post(`/meetings/${PK}/rec/${r.id}/chunk/`, e.data).then(x => { if (!x.ok) throw 0 })).catch(() => toast("Yozuv qismini yuborib bo‘lmadi", "x")) };
    mr.onstop = async () => { const R = rec; rec = null; R.wk.terminate(); await R.q; try { await post(`/meetings/${PK}/rec/stop/`) } catch (_) {} recDest = null; R.after && R.after(); toast("Yozuv saqlandi — meeting tafsilotlarida «Yozuvlar» bo‘limida") };
    drawFrame(); mr.start(5000);
  }
  function stopRec() { if (rec && rec.mr.state !== "inactive") rec.mr.stop() }
  $("#b-rec").onclick = () => { if (rec) KM.ask("Yozib olish to‘xtatilsinmi?", () => { stopRec(); KM.ov("") }); else if (recOn) toast("Yozuv allaqachon ketmoqda", "x"); else startRec() };
  $("#b-allow").onclick = () => { const on = !(defaults.mic && defaults.cam); send({ type: "defaults", mic: on, cam: on }) };

  function renderTile(uid) {
    const r = roster.get(uid); if (!r || (!r.online && uid !== ME)) return;
    let t = $(`#tile-${uid}`);
    if (!t) {
      t = el("div", "mr-tile"); t.id = "tile-" + uid;
      const v = document.createElement("video"); v.autoplay = true; v.playsInline = true; if (uid === ME) v.muted = true;
      const av = el("div", "mr-av"), nm = el("div", "mr-nm"), st = el("div", "mr-st");
      const pin = el("div", "mr-pin", "📌"); pin.hidden = true; t.append(v, av, nm, st, pin); $("#grid").appendChild(t);
      t.onclick = () => { pinned = pinned === uid ? null : uid; if (mode === "grid") mode = "speaker"; layout() }; layout();
      if (uid === ME) { v.srcObject = new MediaStream() }
      else { const P = peers.get(uid); if (P) v.srcObject = P.ms }
    }
    const s = { mic: false, cam: false, screen: false, hand: false, ...(uid === ME ? state : (r.state || {})) };
    const v = $("video", t);
    if (uid === ME) { const ms = v.srcObject; ms.getTracks().forEach(x => ms.removeTrack(x)); const tr = tracks.screen || tracks.cam; if (tr) ms.addTrack(tr) }
    const showVideo = s.cam || s.screen;
    t.classList.toggle("novid", !showVideo); t.classList.toggle("scr", !!s.screen); t.classList.toggle("me", uid === ME);
    $(".mr-av", t).textContent = r.ini || "?"; layout();
    $(".mr-nm", t).textContent = (uid === ME ? "Siz" : r.name) + (r.role === "host" ? " · boshlovchi" : r.role === "cohost" ? " · yordamchi" : "");
    const st = $(".mr-st", t); st.replaceChildren();
    if (s.hand) st.appendChild(ic("hand")); if (!s.mic) st.appendChild(ic("mic-off")); fx();
    if (uid !== ME) { v.play && v.play().catch(() => {}) }
  }

  /* ------------------------------------------------------------------ qatnashchilar paneli */
  function renderPeople() {
    const box = $("#people"); box.replaceChildren();
    const list = [...roster.values()].filter(r => !r.banned).sort((a, b) => (b.online - a.online) || a.name.localeCompare(b.name));
    $("#pc").textContent = list.filter(r => r.online).length;
    list.forEach(r => {
      const row = el("div", "mr-pr" + (r.online ? "" : " off")), top = el("div", "row");
      top.style.flexWrap = "nowrap"; top.append(el("div", "av", r.ini));
      const nm = el("div", "sp"); const b = el("b", "", r.uid === ME ? r.name + " (siz)" : r.name); nm.append(b, el("div", "m", "@" + r.username + (r.role === "host" ? " · boshlovchi" : r.role === "cohost" ? " · yordamchi" : "") + (r.online ? "" : " · xonada emas")));
      top.append(nm);
      const s = r.uid === ME ? state : (r.state || {});
      if (s.hand) { const h = ic("hand"); h.style.color = "var(--dg)"; top.append(h) }
      if (r.online) top.append(ic(s.mic ? "mic" : "mic-off"));
      row.append(top);
      const target = r.uid !== ME && r.role !== "host";
      const acts = el("div", "mr-acts");
      const btn = (icon, title, fn, cls) => { const x = el("button", "ib2 " + (cls || "")); x.type = "button"; x.title = title; x.append(ic(icon)); x.onclick = fn; acts.append(x) };
      if (target && r.online && perms.mute) { btn("mic-off", "Mikrofonni o‘chirish", () => send({ type: "mute", uid: r.uid, what: "mic" })); btn("video-off", "Kamerani o‘chirish", () => send({ type: "mute", uid: r.uid, what: "cam" })) }
      if (target && s.hand && perms.grant) btn("mic", "Gapirishga ruxsat berish (qo‘l tushadi)", () => { send({ type: "grant", uid: r.uid, mic: true, cam: true }); send({ type: "lower_hand", uid: r.uid }) }, "ok");
      if (target && s.hand && (me.role !== "member")) btn("arrow-down", "Qo‘lni tushirish", () => send({ type: "lower_hand", uid: r.uid }));
      if (target && perms.grant && r.role !== "cohost") {
        const c = r.caps || {};
        btn(c.mic ? "mic" : "mic-off", c.mic ? "Mikrofon ruxsatini olib qo‘yish" : "Mikrofon ruxsati berish", () => send({ type: "grant", uid: r.uid, mic: !c.mic }), c.mic ? "" : "dg");
        btn(c.cam ? "video" : "video-off", c.cam ? "Kamera ruxsatini olib qo‘yish" : "Kamera ruxsati berish", () => send({ type: "grant", uid: r.uid, cam: !c.cam }), c.cam ? "" : "dg");
        btn("monitor", c.screen ? "Ekran ruxsatini olib qo‘yish" : "Ekran ulashishga ruxsat berish", () => send({ type: "grant", uid: r.uid, screen: !c.screen }), c.screen ? "" : "dg");
        btn("message-square", c.chat ? "Yozishni taqiqlash" : "Yozishga ruxsat berish", () => send({ type: "grant", uid: r.uid, chat: !c.chat }), c.chat ? "" : "dg");
      }
      if (target && perms.kick && r.role !== "cohost" || (target && perms.kick && me.role === "host")) btn("user-x", "Meetingdan chiqarib yuborish", () => KM.ask(`${r.name} meetingdan chiqarilsinmi?`, () => { send({ type: "kick", uid: r.uid }); KM.ov("") }), "dg");
      if (acts.children.length) row.append(acts);
      box.append(row);
    });
    fx();
  }

  /* ------------------------------------------------------------------ chat + @belgilash */
  const msgs = $("#msgs"), nearBottom = () => msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight < 80, scroll = () => { msgs.scrollTop = msgs.scrollHeight };
  const MENT = /(@[A-Za-z0-9_.]{3,30})/g;
  function addMsg(c, silent) {
    const stick = nearBottom();
    const m = el("div", "mr-m" + (c.uid === ME ? " me" : "") + (c.deleted ? " del" : "")); m.dataset.id = c.id;
    const h = el("div", "mr-mh"); h.append(el("b", "", c.uid === ME ? "Siz" : c.name), el("span", "m", c.at));
    const canDel = !c.deleted && (c.uid === ME || perms.comments);
    if (canDel) { const x = el("button", "ib2 mr-x"); x.type = "button"; x.title = "Izohni o‘chirish"; x.append(ic("trash-2")); x.onclick = () => send({ type: "delete_comment", id: c.id }); h.append(x) }
    const b = el("div", "mr-mb");
    if (c.deleted) { b.textContent = "Izoh o‘chirildi"; b.classList.add("m") }
    else c.text.split(MENT).forEach(p => {
      if (MENT.test(p)) { MENT.lastIndex = 0; const un = p.slice(1).toLowerCase(), mine = me && un === me.username.toLowerCase(); const s = el("span", "mr-tag" + (mine ? " me" : ""), p); b.append(s) }
      else b.append(document.createTextNode(p));
      MENT.lastIndex = 0;
    });
    m.append(h, b); msgs.append(m); fx();
    if (stick || c.uid === ME) scroll();
    if (!silent && c.uid !== ME && $("#side").classList.contains("closed")) { unread++; const d = $("#mr-unread"); d.textContent = unread; d.hidden = false }
  }
  function delMsg(id) {
    const m = $(`.mr-m[data-id="${id}"]`, msgs); if (!m) return;
    m.classList.add("del"); $(".mr-mb", m).replaceChildren(document.createTextNode("Izoh o‘chirildi")); $(".mr-mb", m).classList.add("m"); const x = $(".mr-x", m); x && x.remove();
  }
  $("#cform").onsubmit = e => { e.preventDefault(); const i = $("#ctext"), t = i.value.trim(); if (!t || i.disabled) return; send({ type: "chat", text: t }); i.value = ""; hideMention() };

  const mbox = $("#mention"); let mSel = 0, mList = [];
  function hideMention() { mbox.hidden = true; mList = [] }
  function mentionState() { const i = $("#ctext"), pos = i.selectionStart, m = /(^|\s)@([A-Za-z0-9_.]{0,30})$/.exec(i.value.slice(0, pos)); return m ? { q: m[2].toLowerCase(), start: pos - m[2].length - 1, pos } : null }
  function showMention() {
    const s = mentionState(); if (!s) return hideMention();
    mList = mentionables.filter(u => u.username !== (me && me.username) && (u.username.toLowerCase().includes(s.q) || u.name.toLowerCase().includes(s.q))).slice(0, 6);
    if (!mList.length) return hideMention();
    mSel = Math.min(mSel, mList.length - 1); mbox.replaceChildren();
    mList.forEach((u, i) => { const o = el("div", "mr-mo" + (i === mSel ? " on" : "")); o.append(el("b", "", u.name), el("span", "m", " @" + u.username)); o.onmousedown = ev => { ev.preventDefault(); pickMention(u) }; mbox.append(o) });
    mbox.hidden = false;
  }
  function pickMention(u) {
    const i = $("#ctext"), s = mentionState(); if (!s) return;
    i.value = i.value.slice(0, s.start) + "@" + u.username + " " + i.value.slice(s.pos); const p = s.start + u.username.length + 2; i.setSelectionRange(p, p); hideMention(); i.focus();
  }
  $("#ctext").addEventListener("input", showMention);
  $("#ctext").addEventListener("keydown", e => {
    if (mbox.hidden) return;
    if (e.key === "ArrowDown") { e.preventDefault(); mSel = (mSel + 1) % mList.length; showMention() }
    else if (e.key === "ArrowUp") { e.preventDefault(); mSel = (mSel - 1 + mList.length) % mList.length; showMention() }
    else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pickMention(mList[mSel]) }
    else if (e.key === "Escape") hideMention();
  });
  $("#ctext").addEventListener("blur", () => setTimeout(hideMention, 100));

  /* ------------------------------------------------------------------ yon panel */
  $$("[data-tab]").forEach(b => b.onclick = () => { $$("[data-tab]").forEach(x => x.classList.toggle("on", x === b)); $("#pane-chat").hidden = b.dataset.tab !== "chat"; $("#pane-people").hidden = b.dataset.tab !== "people"; if (b.dataset.tab === "chat") { unread = 0; $("#mr-unread").hidden = true } });
  $("#tg-panel").onclick = () => { const s = $("#side"); s.classList.toggle("closed"); if (!s.classList.contains("closed")) { unread = 0; $("#mr-unread").hidden = true } };
  if (matchMedia("(max-width:800px)").matches) $("#side").classList.add("closed");
  fx();
})();
