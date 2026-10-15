(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const MAX_IMAGE = 20 * 1024 * 1024;    // 20 MB for fundus image
  const MAX_NOTE_FILE = 10 * 1024 * 1024; // 10 MB for medical note file
  const MAX_NOTE = 4000;

  const NOTE_ACCEPT = new Set([
    "image/png", "image/jpeg",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ]);

  const state = { file: null, previewUrl: null, caseId: null, noteFile: null };

  /* ---------- helpers ---------- */
  function toast(message, kind = "error") {
    const el = document.createElement("div");
    el.className = "toast" + (kind === "ok" ? " ok" : "");

    const iconEl = document.createElement("div");
    iconEl.className = "toast-icon";
    iconEl.innerHTML = kind === "ok"
      ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
      : '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

    const textEl = document.createElement("span");
    textEl.textContent = message;

    el.appendChild(iconEl);
    el.appendChild(textEl);
    $("#toasts").appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }

  function show(view) {
    $("#landing").hidden = view !== "landing";
    $("#app").hidden = view !== "app";
    $("#user-chip").hidden = view !== "app";
  }

  async function api(path, options = {}) {
    const res = await fetch(path, { credentials: "same-origin", ...options });
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-JSON body */ }
    if (!res.ok) {
      let msg = data && (data.error || data.detail);
      if (typeof msg !== "string") msg = `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  }

  function waitFor(test, timeoutMs = 10000) {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      (function poll() {
        if (test()) return resolve();
        if (Date.now() - start > timeoutMs) return reject(new Error("timeout"));
        setTimeout(poll, 100);
      })();
    });
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  /* ---------- auth ---------- */
  function enterApp(user) {
    $("#user-name").textContent = user.name || user.email;
    const pic = $("#user-pic");
    if (user.picture) { pic.src = user.picture; pic.hidden = false; } else { pic.hidden = true; }
    show("app");
  }

  async function onCredential(response) {
    try {
      const user = await api("/api/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_token: response.credential }),
      });
      enterApp(user);
    } catch (e) {
      toast(e.message);
    }
  }

  async function initGoogle(cfg) {
    if (!cfg.google_client_id) {
      toast("GOOGLE_CLIENT_ID is not configured on the server.");
      return;
    }
    try {
      await waitFor(() => window.google && google.accounts && google.accounts.id);
    } catch (_) {
      toast("Could not load Google Sign-In. Check your connection and reload.");
      return;
    }
    google.accounts.id.initialize({ client_id: cfg.google_client_id, callback: onCredential });
    google.accounts.id.renderButton($("#google-btn"), {
      theme: "filled_blue", size: "large", shape: "pill", text: "signin_with", width: 280,
    });
  }

  async function logout() {
    try { await api("/api/auth/logout", { method: "POST" }); } catch (_) { /* ignore */ }
    if (window.google && google.accounts && google.accounts.id) google.accounts.id.disableAutoSelect();
    resetCase();
    show("landing");
  }

  /* ---------- fundus image upload ---------- */
  function setFile(file) {
    if (!file) return;
    if (!["image/jpeg", "image/png"].includes(file.type)) {
      toast("Please choose a JPEG or PNG fundus image.");
      return;
    }
    if (file.size > MAX_IMAGE) {
      toast("That image is larger than 20 MB.");
      return;
    }
    state.file = file;
    if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
    state.previewUrl = URL.createObjectURL(file);
    $("#preview").src = state.previewUrl;
    $("#preview").hidden = false;
    $("#drop-hint").hidden = true;
    updateGenerateBtn();
  }

  /* ---------- medical note file upload ---------- */
  function setNoteFile(file) {
    if (!file) return;
    if (!NOTE_ACCEPT.has(file.type)) {
      toast("Unsupported file type. Upload PNG, JPEG, PDF, or Word documents.");
      return;
    }
    if (file.size > MAX_NOTE_FILE) {
      toast("Note file is larger than 10 MB.");
      return;
    }
    state.noteFile = file;
    // Show attached chip, hide upload hint
    $("#note-drop-hint").hidden = true;
    $("#note-file-attached").hidden = false;
    $("#note-file-name").textContent = file.name;
    $("#note-file-size").textContent = formatBytes(file.size);
  }

  function removeNoteFile() {
    state.noteFile = null;
    $("#note-file").value = "";
    $("#note-drop-hint").hidden = false;
    $("#note-file-attached").hidden = true;
    $("#note-file-name").textContent = "";
    $("#note-file-size").textContent = "";
  }

  function updateGenerateBtn() {
    $("#generate-btn").disabled = !state.file;
  }

  function resetCase() {
    state.file = null;
    state.caseId = null;
    state.noteFile = null;
    $("#preview").hidden = true;
    $("#drop-hint").hidden = false;
    $("#file").value = "";
    updateGenerateBtn();
    $("#report-content").innerHTML = "";
    $("#report-wrap").hidden = true;
    $("#report-empty").hidden = false;
    $("#export-btn").disabled = true;
    removeNoteFile();
    $("#note").value = "";
    $("#note-count").textContent = "0";
    resetPipeline();
  }

  /* ---------- pipeline progress ---------- */
  const STEPS = ["step-vision", "step-specialists", "step-director", "step-critic", "step-final"];
  let pipelineTimer = null;

  function resetPipeline() {
    $("#pipeline-progress").hidden = true;
    STEPS.forEach((id) => {
      const el = $("#" + id);
      el.classList.remove("active", "done");
    });
    document.querySelectorAll(".pipeline-connector").forEach((el) => el.classList.remove("done"));
    if (pipelineTimer) { clearInterval(pipelineTimer); pipelineTimer = null; }
  }

  function startPipelineAnimation() {
    const panel = $("#pipeline-progress");
    panel.hidden = false;
    let current = 0;
    const connectors = document.querySelectorAll(".pipeline-connector");

    function advance() {
      if (current >= STEPS.length) {
        clearInterval(pipelineTimer);
        pipelineTimer = null;
        return;
      }
      // Mark previous as done
      if (current > 0) {
        const prev = $("#" + STEPS[current - 1]);
        prev.classList.remove("active");
        prev.classList.add("done");
        if (connectors[current - 1]) connectors[current - 1].classList.add("done");
      }
      // Mark current as active
      const cur = $("#" + STEPS[current]);
      cur.classList.add("active");
      current++;
    }

    advance(); // Start immediately
    // Roughly 8-12 seconds per step to cover ~40-60 seconds total
    pipelineTimer = setInterval(advance, 9000);
  }

  function completePipeline() {
    if (pipelineTimer) { clearInterval(pipelineTimer); pipelineTimer = null; }
    const connectors = document.querySelectorAll(".pipeline-connector");
    STEPS.forEach((id, i) => {
      const el = $("#" + id);
      el.classList.remove("active");
      el.classList.add("done");
      if (connectors[i]) connectors[i].classList.add("done");
    });
  }

  function setBusy(busy) {
    $("#spinner").hidden = !busy;
    $("#generate-label").textContent = busy ? "Generating…" : "Generate Report";
    $("#generate-btn").disabled = busy || !state.file;
    if (busy) {
      startPipelineAnimation();
    }
  }

  /* ---------- report ---------- */
  function renderReport(report) {
    const html = DOMPurify.sanitize(marked.parse(report.report_markdown, { gfm: true }));
    $("#report-content").innerHTML = html;
    $("#report-empty").hidden = true;
    $("#report-wrap").hidden = false;
    $("#export-btn").disabled = false;

    // Scroll report into view on mobile
    if (window.innerWidth <= 960) {
      $("#report-card").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  async function generate() {
    if (!state.file) return;
    const note = $("#note").value.trim();
    if (note.length > MAX_NOTE) {
      toast(`The medical note is too long (max ${MAX_NOTE} characters).`);
      return;
    }
    const form = new FormData();
    form.append("image", state.file);
    form.append("note", note);
    form.append("laterality", $("#laterality").value);

    // Attach note file if present
    if (state.noteFile) {
      form.append("note_file", state.noteFile);
    }

    setBusy(true);
    try {
      const report = await api("/api/cases", { method: "POST", body: form });
      state.caseId = report.case_id;
      completePipeline();
      renderReport(report);
      toast(
        report.status === "verified"
          ? "Report generated and verified."
          : "Report generated — unverified, see issues.",
        "ok"
      );
    } catch (e) {
      if (e.status === 401) {
        show("landing");
        toast("Your session expired. Please sign in again.");
      } else {
        toast(e.message);
      }
      resetPipeline();
    } finally {
      setBusy(false);
    }
  }

  function exportPdf() {
    const el = $("#report-content");
    if (!state.caseId || !el.innerHTML) return;

    // Clone the report into an off-screen container with black-on-white styling
    const clone = el.cloneNode(true);
    const wrapper = document.createElement("div");
    wrapper.style.cssText = `
      position: fixed; left: -9999px; top: 0;
      width: 794px;
      background: #ffffff;
      color: #000000;
      font-family: 'Inter', system-ui, sans-serif;
      padding: 24px;
    `;
    // Force all text inside the clone to be black on white
    const style = document.createElement("style");
    style.textContent = `
      .pdf-export-clone, .pdf-export-clone * {
        color: #000000 !important;
        background: #ffffff !important;
        border-color: #cccccc !important;
        -webkit-text-fill-color: #000000 !important;
        box-shadow: none !important;
        text-shadow: none !important;
      }
      .pdf-export-clone h1 {
        border-bottom: 2px solid #000000 !important;
      }
      .pdf-export-clone h2 {
        color: #111111 !important;
        -webkit-text-fill-color: #111111 !important;
      }
      .pdf-export-clone blockquote {
        background: #f5f5f5 !important;
        border-left: 3px solid #666666 !important;
        color: #333333 !important;
        -webkit-text-fill-color: #333333 !important;
      }
      .pdf-export-clone code {
        background: #f0f0f0 !important;
        color: #222222 !important;
        -webkit-text-fill-color: #222222 !important;
      }
      .pdf-export-clone th {
        background: #e8e8e8 !important;
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
      }
      .pdf-export-clone td {
        color: #000000 !important;
        -webkit-text-fill-color: #000000 !important;
      }
      .pdf-export-clone hr {
        border-top-color: #cccccc !important;
      }
    `;
    clone.classList.add("pdf-export-clone");
    wrapper.appendChild(style);
    wrapper.appendChild(clone);
    document.body.appendChild(wrapper);

    html2pdf().set({
      margin: 12,
      filename: `consilium-report-${state.caseId.slice(0, 8)}.pdf`,
      image: { type: "jpeg", quality: 0.98 },
      html2canvas: { scale: 2, useCORS: true, backgroundColor: "#ffffff" },
      jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
    }).from(clone).save().then(() => {
      document.body.removeChild(wrapper);
    });
  }

  /* ---------- wiring ---------- */
  function wire() {
    // Fundus image dropzone
    const dz = $("#dropzone");
    const input = $("#file");
    dz.addEventListener("click", () => input.click());
    dz.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
    });
    input.addEventListener("change", () => setFile(input.files[0]));
    ["dragenter", "dragover"].forEach((ev) =>
      dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) =>
      dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
    dz.addEventListener("drop", (e) => setFile(e.dataTransfer.files[0]));

    // Medical note file dropzone
    const ndz = $("#note-dropzone");
    const noteInput = $("#note-file");
    ndz.addEventListener("click", (e) => {
      // Don't re-trigger if clicking the remove button
      if (e.target.closest("#note-remove-btn")) return;
      noteInput.click();
    });
    ndz.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); noteInput.click(); }
    });
    noteInput.addEventListener("change", () => setNoteFile(noteInput.files[0]));
    ["dragenter", "dragover"].forEach((ev) =>
      ndz.addEventListener(ev, (e) => { e.preventDefault(); ndz.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) =>
      ndz.addEventListener(ev, (e) => { e.preventDefault(); ndz.classList.remove("drag"); }));
    ndz.addEventListener("drop", (e) => setNoteFile(e.dataTransfer.files[0]));

    // Remove note file button
    $("#note-remove-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      removeNoteFile();
    });

    // Text note
    $("#note").addEventListener("input", (e) => {
      $("#note-count").textContent = e.target.value.length;
    });

    // Buttons
    $("#generate-btn").addEventListener("click", generate);
    $("#export-btn").addEventListener("click", exportPdf);
    $("#logout-btn").addEventListener("click", logout);
  }

  async function init() {
    wire();
    let cfg = { google_client_id: "", vision_mode: "live" };
    try { cfg = await api("/api/config"); } catch (e) { toast(e.message); }
    $("#mock-tag").hidden = cfg.vision_mode !== "mock";

    try {
      enterApp(await api("/api/me"));
    } catch (_) {
      show("landing");
      initGoogle(cfg);
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();