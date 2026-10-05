"use strict";

(() => {
  const table = document.getElementById("job-table");
  const rows = Array.from(table.querySelectorAll("tr[data-job-id]"));
  const search = document.getElementById("job-search");
  const source = document.getElementById("job-source");
  const status = document.getElementById("job-status");
  const minScore = document.getElementById("job-min-score");
  let sortKey = "", ascending = true;

  function filterRows() {
    const query = search.value.trim().toLowerCase();
    let count = 0;
    rows.forEach(row => {
      const data = row.dataset;
      const text = `${data.title} ${data.company} ${data.location}`.toLowerCase();
      row.hidden = !text.includes(query) || (source.value && data.source !== source.value) ||
        (status.value && data.status !== status.value) ||
        (minScore.value !== "" && (data.score === "" || Number(data.score) < Number(minScore.value)));
      if (!row.hidden) count++;
    });
    document.getElementById("job-count").textContent = `${count} of ${rows.length} jobs`;
    document.getElementById("no-jobs").hidden = count > 0;
  }

  [search, source, status, minScore].forEach(input => input.addEventListener("input", filterRows));
  document.getElementById("reset-filters").addEventListener("click", () => {
    search.value = source.value = status.value = minScore.value = "";
    filterRows();
  });
  table.querySelectorAll("button[data-sort]").forEach(button => button.addEventListener("click", () => {
    ascending = sortKey === button.dataset.sort ? !ascending : true;
    sortKey = button.dataset.sort;
    const sorted = rows.slice().sort((left, right) => {
      const a = left.dataset[sortKey], b = right.dataset[sortKey];
      if (a === "" || b === "") return a === b ? 0 : a === "" ? 1 : -1;
      const comparison = sortKey === "score" ? Number(a) - Number(b) : a.localeCompare(b, undefined, { numeric: true });
      return comparison * (ascending ? 1 : -1);
    });
    sorted.forEach(row => table.tBodies[0].appendChild(row));
    table.tBodies[0].appendChild(document.getElementById("no-jobs"));
    table.querySelectorAll("th[aria-sort]").forEach(th => th.setAttribute("aria-sort", "none"));
    button.closest("th").setAttribute("aria-sort", ascending ? "ascending" : "descending");
  }));
  filterRows();
})();
