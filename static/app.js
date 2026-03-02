// UI element references used across interactions.
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("fileInput");
const folderInput = document.getElementById("folderInput");
const uploadBtn = document.getElementById("uploadBtn");
const clearBtn = document.getElementById("clearBtn");
const selectedList = document.getElementById("selectedList");

const statusLine = document.getElementById("statusLine");
const statusHint = document.getElementById("statusHint");

const outputsList = document.getElementById("outputsList");

const previewThead = document.getElementById("previewThead");
const previewTbody = document.getElementById("previewTbody");
const previewEmpty = document.getElementById("previewEmpty");
const activeFilePill = document.getElementById("activeFilePill");
const activeRowsPill = document.getElementById("activeRowsPill");
const downloadBtn = document.getElementById("downloadBtn");

// Frontend state: selected uploads and currently previewed output id.
let selectedFiles = [];
let activeFileId = null;

function fmtBytes(bytes) {
  // Human-readable byte sizes for list metadata.
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function setStatus(line, hint = "") {
  // Centralized status UI updates.
  statusLine.textContent = line;
  statusHint.textContent = hint || "";
}

function onlyPdfs(files) {
  // Accept only .pdf files from all input methods.
  return files.filter((f) => (f.name || "").toLowerCase().endsWith(".pdf"));
}

function addFiles(files) {
  const incoming = onlyPdfs(Array.from(files || []));
  if (!incoming.length) return;

  // De-dupe by name+size+lastModified
  const key = (f) => `${f.name}::${f.size}::${f.lastModified}`;
  const existing = new Set(selectedFiles.map(key));
  for (const f of incoming) {
    if (!existing.has(key(f))) selectedFiles.push(f);
  }

  renderSelected();
}

function renderSelected() {
  selectedList.innerHTML = "";

  if (!selectedFiles.length) {
    uploadBtn.disabled = true;
    clearBtn.disabled = true;
    setStatus("Ready.", "Tip: you can upload multiple statements at once.");
    return;
  }

  uploadBtn.disabled = false;
  clearBtn.disabled = false;
  setStatus(`Selected ${selectedFiles.length} PDF(s).`, "Click “Parse to CSV” when you’re ready.");

  for (const f of selectedFiles) {
    const li = document.createElement("li");
    li.className = "file";

    const name = document.createElement("div");
    name.className = "file-name";
    name.textContent = f.webkitRelativePath ? f.webkitRelativePath : f.name;

    const meta = document.createElement("div");
    meta.className = "file-meta";
    meta.textContent = `${fmtBytes(f.size)} • ${new Date(f.lastModified).toLocaleString()}`;

    li.appendChild(name);
    li.appendChild(meta);
    selectedList.appendChild(li);
  }
}

async function fetchOutputs() {
  // Pull generated CSV inventory from backend.
  const res = await fetch("/api/files");
  const data = await res.json();
  renderOutputs(data.files || []);
}

function renderOutputs(files) {
  outputsList.innerHTML = "";

  if (!files.length) {
    const div = document.createElement("div");
    div.className = "empty";
    div.textContent = "No CSVs generated yet.";
    outputsList.appendChild(div);
    return;
  }

  for (const f of files) {
    const item = document.createElement("div");
    item.className = `out-item ${activeFileId === f.id ? "active" : ""}`;
    item.tabIndex = 0;

    const name = document.createElement("div");
    name.className = "out-name";
    name.textContent = f.filename;

    const meta = document.createElement("div");
    meta.className = "out-meta";
    meta.textContent = `${fmtBytes(f.size)}`;

    item.appendChild(name);
    item.appendChild(meta);

    item.addEventListener("click", () => selectOutput(f.id));
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") selectOutput(f.id);
    });

    outputsList.appendChild(item);
  }
}

function clearPreview() {
  // Reset preview table/pills when no file is active.
  activeFileId = null;
  previewThead.innerHTML = "";
  previewTbody.innerHTML = "";
  previewEmpty.style.display = "block";
  activeFilePill.textContent = "No file selected";
  activeRowsPill.textContent = "— rows";
  downloadBtn.disabled = true;
  renderOutputsFromDomActive();
}

function renderOutputsFromDomActive() {
  // Reapply active style without refetching.
  const nodes = Array.from(outputsList.querySelectorAll(".out-item"));
  for (const n of nodes) {
    const name = n.querySelector(".out-name")?.textContent || "";
    const isActive = activeFileId && name && n.classList.contains("active");
    if (!isActive) n.classList.remove("active");
  }
}

async function selectOutput(fileId) {
  // Load and render one output CSV preview.
  activeFileId = fileId;
  downloadBtn.disabled = false;
  downloadBtn.onclick = () => {
    window.location.href = `/api/files/${encodeURIComponent(activeFileId)}/download`;
  };

  setStatus("Loading preview…", "");

  const res = await fetch(`/api/files/${encodeURIComponent(fileId)}/preview?limit=80`);
  if (!res.ok) {
    setStatus("Could not load preview.", "Try re-parsing the statement.");
    return;
  }

  const data = await res.json();

  activeFilePill.textContent = data.filename || "CSV";
  activeRowsPill.textContent = `${(data.rows || []).length} rows (preview)`;

  const cols = data.columns || [];
  const rows = data.rows || [];

  previewThead.innerHTML = "";
  previewTbody.innerHTML = "";

  const trh = document.createElement("tr");
  for (const c of cols) {
    const th = document.createElement("th");
    th.textContent = c;
    trh.appendChild(th);
  }
  previewThead.appendChild(trh);

  for (const r of rows) {
    const tr = document.createElement("tr");
    for (const c of cols) {
      const td = document.createElement("td");
      const v = r[c];
      td.textContent = v === null || v === undefined ? "" : String(v);
      tr.appendChild(td);
    }
    previewTbody.appendChild(tr);
  }

  previewEmpty.style.display = rows.length ? "none" : "block";

  // Update active styling
  const items = Array.from(outputsList.querySelectorAll(".out-item"));
  for (const item of items) item.classList.remove("active");
  // best-effort: find by click order (we'll refresh list after parse anyway)
  // user experience is fine without perfect DOM mapping.

  setStatus("Preview loaded.", "Use “Download CSV” to save it.");
  await fetchOutputs(); // refresh list and apply proper active state via id matching
}

async function uploadSelected() {
  // Send all selected PDFs in one multipart request.
  if (!selectedFiles.length) return;

  uploadBtn.disabled = true;
  clearBtn.disabled = true;
  setStatus("Uploading PDFs…", "Parsing can take a few seconds per statement.");

  const form = new FormData();
  for (const f of selectedFiles) form.append("files", f, f.name);

  const res = await fetch("/api/parse", { method: "POST", body: form });
  const data = await res.json();

  const created = data.created || [];
  const errors = data.errors || [];

  if (errors.length) {
    const msg = errors.length === 1 ? errors[0].error : `${errors.length} files failed to parse.`;
    setStatus("Done (with some errors).", msg);
  } else {
    setStatus("Done.", `Generated ${created.length} CSV(s).`);
  }

  selectedFiles = [];
  renderSelected();
  await fetchOutputs();

  if (created.length) {
    // Auto-select most recent created
    const first = created[0];
    if (first?.id) await selectOutput(first.id);
  }
}

// Dropzone interactions
dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  addFiles(e.dataTransfer.files);
});

fileInput.addEventListener("change", () => addFiles(fileInput.files));
folderInput.addEventListener("change", () => addFiles(folderInput.files));

clearBtn.addEventListener("click", () => {
  selectedFiles = [];
  fileInput.value = "";
  folderInput.value = "";
  renderSelected();
});

uploadBtn.addEventListener("click", uploadSelected);

downloadBtn.addEventListener("click", () => {
  if (!activeFileId) return;
  window.location.href = `/api/files/${encodeURIComponent(activeFileId)}/download`;
});

// Initial load
renderSelected();
fetchOutputs().catch(() => {});
clearPreview();

