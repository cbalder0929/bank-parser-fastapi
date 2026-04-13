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
const selectAllCb = document.getElementById("selectAllCb");
const clearOutputsBtn = document.getElementById("clearOutputsBtn");

const previewThead = document.getElementById("previewThead");
const previewTbody = document.getElementById("previewTbody");
const previewEmpty = document.getElementById("previewEmpty");
const activeFilePill = document.getElementById("activeFilePill");
const activeRowsPill = document.getElementById("activeRowsPill");
const downloadBtn = document.getElementById("downloadBtn");

// Frontend state: selected uploads, currently previewed output id, and checked output ids.
let selectedFiles = [];
let activeFileId = null;
let checkedIds = new Set();
// Cache the latest file list from the server.
let outputFilesList = [];

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

function acceptedFiles(files) {
  // Accept .pdf and .csv files from all input methods.
  return files.filter((f) => {
    const name = (f.name || "").toLowerCase();
    return name.endsWith(".pdf") || name.endsWith(".csv");
  });
}

function addFiles(files) {
  const incoming = acceptedFiles(Array.from(files || []));
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
    setStatus("Ready.", "Tip: you can upload PDFs and CSVs at once.");
    return;
  }

  uploadBtn.disabled = false;
  clearBtn.disabled = false;
  setStatus(
    `Selected ${selectedFiles.length} file(s).`,
    "Click \u201cParse / Upload\u201d when you\u2019re ready."
  );

  for (const f of selectedFiles) {
    const li = document.createElement("li");
    li.className = "file";

    const name = document.createElement("div");
    name.className = "file-name";
    name.textContent = f.webkitRelativePath ? f.webkitRelativePath : f.name;

    const meta = document.createElement("div");
    meta.className = "file-meta";
    meta.textContent = `${fmtBytes(f.size)} \u2022 ${new Date(f.lastModified).toLocaleString()}`;

    li.appendChild(name);
    li.appendChild(meta);
    selectedList.appendChild(li);
  }
}

function updateDownloadBtn() {
  downloadBtn.disabled = checkedIds.size === 0;
  if (checkedIds.size > 1) {
    downloadBtn.textContent = `Download Selected (${checkedIds.size})`;
  } else {
    downloadBtn.textContent = "Download Selected";
  }
}

function updateSelectAllCb() {
  if (!outputFilesList.length) {
    selectAllCb.checked = false;
    selectAllCb.indeterminate = false;
    return;
  }
  const allChecked = outputFilesList.every((f) => checkedIds.has(f.id));
  const someChecked = outputFilesList.some((f) => checkedIds.has(f.id));
  selectAllCb.checked = allChecked;
  selectAllCb.indeterminate = !allChecked && someChecked;
}

async function fetchOutputs() {
  // Pull generated CSV inventory from backend.
  const res = await fetch("/api/files");
  const data = await res.json();
  outputFilesList = data.files || [];

  if (activeFileId && !outputFilesList.some((f) => f.id === activeFileId)) {
    activeFileId = null;
  }

  checkedIds = new Set(outputFilesList.filter((f) => checkedIds.has(f.id)).map((f) => f.id));
  clearOutputsBtn.disabled = outputFilesList.length === 0;
  renderOutputs(outputFilesList);
}

function renderOutputs(files) {
  outputsList.innerHTML = "";

  if (!files.length) {
    const div = document.createElement("div");
    div.className = "empty";
    div.textContent = "No CSVs generated yet.";
    outputsList.appendChild(div);
    updateSelectAllCb();
    updateDownloadBtn();
    return;
  }

  for (const f of files) {
    const item = document.createElement("div");
    item.className = `out-item ${activeFileId === f.id ? "active" : ""}`;
    item.tabIndex = 0;

    const cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "out-cb";
    cb.checked = checkedIds.has(f.id);
    cb.addEventListener("change", (e) => {
      e.stopPropagation();
      if (cb.checked) {
        checkedIds.add(f.id);
      } else {
        checkedIds.delete(f.id);
      }
      updateDownloadBtn();
      updateSelectAllCb();
    });
    cb.addEventListener("click", (e) => e.stopPropagation());

    const name = document.createElement("div");
    name.className = "out-name";
    name.textContent = f.filename;

    const meta = document.createElement("div");
    meta.className = "out-meta";
    meta.textContent = `${fmtBytes(f.size)}`;

    const textWrap = document.createElement("div");
    textWrap.className = "out-text";
    textWrap.appendChild(name);
    textWrap.appendChild(meta);

    item.appendChild(cb);
    item.appendChild(textWrap);

    item.addEventListener("click", () => selectOutput(f.id));
    item.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") selectOutput(f.id);
    });

    outputsList.appendChild(item);
  }

  updateSelectAllCb();
  updateDownloadBtn();
}

function clearPreview() {
  // Reset preview table/pills when no file is active.
  activeFileId = null;
  previewThead.innerHTML = "";
  previewTbody.innerHTML = "";
  previewEmpty.style.display = "block";
  activeFilePill.textContent = "No file selected";
  activeRowsPill.textContent = "\u2014 rows";
  updateDownloadBtn();
}

async function selectOutput(fileId) {
  // Load and render one output CSV preview.
  activeFileId = fileId;

  // Auto-check the previewed file if nothing is checked yet.
  if (!checkedIds.has(fileId) && checkedIds.size === 0) {
    checkedIds.add(fileId);
  }
  updateDownloadBtn();

  setStatus("Loading preview\u2026", "");

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

  setStatus("Preview loaded.", "Select CSVs and click \u201cDownload Selected\u201d.");
  await fetchOutputs(); // refresh list and apply proper active state via id matching
}

async function downloadSelected() {
  if (checkedIds.size === 0) return;

  const ids = Array.from(checkedIds);

  if (ids.length === 1) {
    // Single file: direct download.
    window.location.href = `/api/files/${encodeURIComponent(ids[0])}/download`;
    return;
  }

  // Multiple files: combine via POST.
  setStatus("Combining CSVs\u2026", "");
  const res = await fetch("/api/files/combine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  });

  if (!res.ok) {
    setStatus("Download failed.", "Could not combine selected CSVs.");
    return;
  }

  // Trigger file save from the response blob.
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "combined_statements.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);

  setStatus("Download started.", "combined_statements.csv");
}

async function uploadSelected() {
  // Send all selected files in one multipart request.
  if (!selectedFiles.length) return;

  uploadBtn.disabled = true;
  clearBtn.disabled = true;
  setStatus("Uploading files\u2026", "Parsing can take a few seconds per statement.");

  const form = new FormData();
  for (const f of selectedFiles) form.append("files", f, f.name);

  const res = await fetch("/api/parse", { method: "POST", body: form });
  const data = await res.json();

  const created = data.created || [];
  const errors = data.errors || [];

  if (errors.length) {
    const msg =
      errors.length === 1
        ? errors[0].error
        : `${errors.length} files failed to parse.`;
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

async function clearGeneratedOutputs() {
  if (!outputFilesList.length) return;

  clearOutputsBtn.disabled = true;
  setStatus("Clearing generated CSVs…", "");

  const res = await fetch("/api/files", { method: "DELETE" });
  if (!res.ok) {
    clearOutputsBtn.disabled = false;
    setStatus("Clear failed.", "Could not remove generated CSVs.");
    return;
  }

  checkedIds.clear();
  activeFileId = null;
  clearPreview();
  await fetchOutputs();
  setStatus("Generated CSVs cleared.", "The outputs list is now empty.");
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

downloadBtn.addEventListener("click", downloadSelected);
clearOutputsBtn.addEventListener("click", clearGeneratedOutputs);

selectAllCb.addEventListener("change", () => {
  if (selectAllCb.checked) {
    for (const f of outputFilesList) checkedIds.add(f.id);
  } else {
    checkedIds.clear();
  }
  renderOutputs(outputFilesList);
});

// Initial load
renderSelected();
fetchOutputs().catch(() => {});
clearPreview();
