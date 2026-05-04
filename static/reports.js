const GREEN_PALETTE = [
  "#2e7d32","#388e3c","#43a047","#66bb6a","#81c784","#a5d6a7",
  "#c8e6c9","#1b5e20","#558b2f","#33691e","#827717","#f57f17",
];

let chartCategory = null;
let chartSource = null;
let chartMonthly = null;

function fmt(n) {
  return "$" + Number(n).toLocaleString("en-US", {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

function activeAccounts() {
  return Array.from(document.querySelectorAll(".chip.active")).map(c => c.dataset.slug);
}

function buildQuery() {
  const from = document.getElementById("fromDate").value;
  const to = document.getElementById("toDate").value;
  const accs = activeAccounts();
  const params = new URLSearchParams();
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  if (accs.length) params.set("accounts", accs.join(","));
  return params.toString() ? "?" + params.toString() : "";
}

async function loadSummary(qs) {
  const res = await fetch("/api/reports/summary" + qs);
  const d = await res.json();
  document.querySelector("#kpiIncome .kpi-value").textContent = fmt(d.total_income);
  document.querySelector("#kpiSpending .kpi-value").textContent = fmt(d.total_spending);
  const netEl = document.querySelector("#kpiNet .kpi-value");
  netEl.textContent = fmt(d.net);
  netEl.style.color = d.net >= 0 ? "var(--green)" : "#c95a36";
  document.querySelector("#kpiTopCat .kpi-value").textContent = d.top_category || "—";
}

async function loadByCategory(qs) {
  const res = await fetch("/api/reports/by-category" + qs);
  const d = await res.json();
  const cats = (d.categories || []).filter(c => c.debit_total > 0);

  const emptyEl = document.getElementById("emptyCategory");
  const canvas = document.getElementById("chartCategory");

  if (!cats.length) {
    emptyEl.style.display = "block";
    canvas.style.display = "none";
    if (chartCategory) { chartCategory.destroy(); chartCategory = null; }
    return;
  }
  emptyEl.style.display = "none";
  canvas.style.display = "block";

  const labels = cats.map(c => c.category);
  const data = cats.map(c => c.debit_total);

  if (chartCategory) chartCategory.destroy();
  chartCategory = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{data, backgroundColor: GREEN_PALETTE, borderWidth: 1, borderColor: "rgba(255,255,255,.6)"}],
    },
    options: {
      plugins: {
        legend: {position: "bottom", labels: {font: {size: 11}, padding: 10}},
        tooltip: {callbacks: {label: ctx => ` ${ctx.label}: ${fmt(ctx.raw)}`}},
      },
      cutout: "60%",
    },
  });
}

async function loadBySource(qs) {
  const res = await fetch("/api/reports/summary" + qs);
  const d = await res.json();
  const breakdown = (d.account_breakdown || []).filter(a => a.income > 0);

  const emptyEl = document.getElementById("emptySource");
  const canvas = document.getElementById("chartSource");

  if (!breakdown.length) {
    emptyEl.style.display = "block";
    canvas.style.display = "none";
    if (chartSource) { chartSource.destroy(); chartSource = null; }
    return;
  }
  emptyEl.style.display = "none";
  canvas.style.display = "block";

  const labels = breakdown.map(a => a.source);
  const data = breakdown.map(a => a.income);

  if (chartSource) chartSource.destroy();
  chartSource = new Chart(canvas, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{data, backgroundColor: GREEN_PALETTE, borderWidth: 1, borderColor: "rgba(255,255,255,.6)"}],
    },
    options: {
      plugins: {
        legend: {position: "bottom", labels: {font: {size: 11}, padding: 10}},
        tooltip: {callbacks: {label: ctx => ` ${ctx.label}: ${fmt(ctx.raw)}`}},
      },
      cutout: "60%",
    },
  });
}

async function loadByMonth(qs) {
  const res = await fetch("/api/reports/by-month" + qs);
  const d = await res.json();
  const months = d.months || [];

  const emptyEl = document.getElementById("emptyMonthly");
  const canvas = document.getElementById("chartMonthly");

  if (!months.length) {
    emptyEl.style.display = "block";
    canvas.style.display = "none";
    if (chartMonthly) { chartMonthly.destroy(); chartMonthly = null; }
    return;
  }
  emptyEl.style.display = "none";
  canvas.style.display = "block";

  const labels = months.map(m => m.month);

  if (chartMonthly) chartMonthly.destroy();
  chartMonthly = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {label: "Income", data: months.map(m => m.income), backgroundColor: "rgba(46,125,50,.75)", borderRadius: 4},
        {label: "Spending", data: months.map(m => m.spending), backgroundColor: "rgba(201,90,54,.70)", borderRadius: 4},
      ],
    },
    options: {
      plugins: {
        legend: {position: "top"},
        tooltip: {callbacks: {label: ctx => ` ${ctx.dataset.label}: ${fmt(ctx.raw)}`}},
      },
      scales: {
        x: {grid: {display: false}},
        y: {ticks: {callback: v => "$" + v.toLocaleString()}},
      },
    },
  });
}

async function loadTopItems(qs) {
  const res = await fetch("/api/reports/top-items" + qs);
  const d = await res.json();
  const items = d.items || [];

  const tbody = document.getElementById("topItemsTbody");
  const emptyEl = document.getElementById("emptyTopItems");
  tbody.innerHTML = "";

  if (!items.length) {
    emptyEl.style.display = "block";
    return;
  }
  emptyEl.style.display = "none";

  items.forEach((item, i) => {
    const tr = document.createElement("tr");
    [i + 1, item.item, item.count, fmt(item.total)].forEach(val => {
      const td = document.createElement("td");
      td.textContent = val;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function loadAll() {
  const qs = buildQuery();
  await Promise.all([
    loadSummary(qs),
    loadByCategory(qs),
    loadBySource(qs),
    loadByMonth(qs),
    loadTopItems(qs),
  ]);
}

// Chip toggle
document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => chip.classList.toggle("active"));
});

document.getElementById("applyFilters").addEventListener("click", loadAll);

loadAll().catch(console.error);
