// FitOps Dashboard — shared Chart.js helpers

Chart.defaults.color = "#9ca3af";
Chart.defaults.borderColor = "#1f2937";

/**
 * Render the CTL / ATL / TSB training load chart.
 * @param {string} canvasId
 * @param {string[]} labels  - date strings
 * @param {{ctl: number[], atl: number[], tsb: number[]}} series
 */
function renderTrainingLoadChart(canvasId, labels, series) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "CTL (Fitness)",
          data: series.ctl,
          borderColor: "#60a5fa",
          backgroundColor: "rgba(96,165,250,0.08)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "ATL (Fatigue)",
          data: series.atl,
          borderColor: "#fb923c",
          backgroundColor: "rgba(251,146,60,0.08)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
        },
        {
          label: "TSB (Form)",
          data: series.tsb,
          borderColor: "#4ade80",
          backgroundColor: "rgba(74,222,128,0.08)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          borderDash: [4, 3],
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: { usePointStyle: true, pointStyle: "line", padding: 16 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#1f2937" },
          ticks: {
            maxTicksLimit: 10,
            maxRotation: 0,
          },
        },
        y: {
          grid: { color: "#1f2937" },
          ticks: { callback: (v) => v.toFixed(0) },
        },
      },
    },
  });
}

/**
 * Render weekly training volume bar chart.
 * @param {string} canvasId
 * @param {{week_start: string, distance_km: number, activity_count: number}[]} weeklyData
 */
function renderWeeklyVolumeChart(canvasId, weeklyData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  const labels = weeklyData.map((w) => w.week_start);
  const distances = weeklyData.map((w) => w.distance_km);
  const counts = weeklyData.map((w) => w.activity_count);

  // Compute average for reference line
  const nonZero = distances.filter((d) => d > 0);
  const avg = nonZero.length ? nonZero.reduce((a, b) => a + b, 0) / nonZero.length : 0;

  new Chart(ctx, {
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Distance (km)",
          data: distances,
          backgroundColor: "rgba(249,115,22,0.7)",
          borderColor: "#f97316",
          borderWidth: 1,
          borderRadius: 3,
          yAxisID: "y",
        },
        {
          type: "line",
          label: "Avg km/week",
          data: labels.map(() => parseFloat(avg.toFixed(1))),
          borderColor: "rgba(96,165,250,0.5)",
          borderWidth: 1.5,
          borderDash: [5, 4],
          pointRadius: 0,
          fill: false,
          yAxisID: "y",
        },
        {
          type: "line",
          label: "Activities",
          data: counts,
          borderColor: "#4ade80",
          backgroundColor: "rgba(74,222,128,0.1)",
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          fill: false,
          yAxisID: "y2",
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          labels: { usePointStyle: true, padding: 16 },
        },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.label === "Activities")
                return ` Activities: ${ctx.parsed.y}`;
              return ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)} km`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { color: "#1f2937" },
          ticks: { maxTicksLimit: 12, maxRotation: 45 },
        },
        y: {
          grid: { color: "#1f2937" },
          position: "left",
          title: { display: true, text: "km", color: "#9ca3af" },
          ticks: { callback: (v) => v + " km" },
        },
        y2: {
          grid: { drawOnChartArea: false },
          position: "right",
          title: { display: true, text: "count", color: "#9ca3af" },
          ticks: { stepSize: 1, callback: (v) => v },
        },
      },
    },
  });
}
