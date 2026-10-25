/**
 * analytics.js - Chart.js Visualizations for Urban Parking Demand & Surge Pricing.
 */

let charts = {};

document.addEventListener("DOMContentLoaded", () => {
  initAnalyticsDashboard();

  const refreshBtn = document.getElementById("btn-refresh-analytics");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadAnalyticsData();
      showToast("Analytics charts refreshed from live database.", "info");
    });
  }
});

async function initAnalyticsDashboard() {
  await loadAnalyticsData();
}

async function loadAnalyticsData() {
  try {
    const res = await fetch("/api/analytics/data");
    const json = await res.json();

    if (!json.success || !json.data) return;

    const data = json.data;
    renderOccupancyChart(data.zones);
    renderPricingChart(data.zones);
    renderDistributionChart(data.zones);
    renderTrendChart(data.trends);

  } catch (err) {
    console.error("Failed to load analytics data:", err);
  }
}

// 1. Zone Occupancy Stacked Bar Chart
function renderOccupancyChart(zones) {
  const ctx = document.getElementById("chart-occupancy");
  if (!ctx) return;

  if (charts.occupancy) charts.occupancy.destroy();

  charts.occupancy = new Chart(ctx, {
    type: "bar",
    data: {
      labels: zones.names,
      datasets: [
        {
          label: "Occupied Slots",
          data: zones.occupied,
          backgroundColor: "#DC2626",
          borderRadius: 4
        },
        {
          label: "Available Slots",
          data: zones.available,
          backgroundColor: "#059669",
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" },
        tooltip: { mode: "index", intersect: false }
      },
      scales: {
        x: { stacked: true },
        y: { stacked: true, beginAtZero: true, title: { display: true, text: "Parking Slots" } }
      }
    }
  });
}

// 2. Zone Hourly Rate & Surge Multiplier
function renderPricingChart(zones) {
  const ctx = document.getElementById("chart-pricing");
  if (!ctx) return;

  if (charts.pricing) charts.pricing.destroy();

  charts.pricing = new Chart(ctx, {
    type: "bar",
    data: {
      labels: zones.names,
      datasets: [
        {
          label: "Current Dynamic Rate (₹/hr)",
          data: zones.hourly_rates,
          backgroundColor: "#00A896",
          borderRadius: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" },
        tooltip: {
          callbacks: {
            label: function(context) {
              const idx = context.dataIndex;
              return `Tariff: ₹${context.raw}/hr (Multiplier: ${zones.multipliers[idx]}x)`;
            }
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          title: { display: true, text: "Hourly Rate (₹)" }
        }
      }
    }
  });
}

// 3. City-Wide Parking Distribution (Donut Chart)
function renderDistributionChart(zones) {
  const ctx = document.getElementById("chart-distribution");
  if (!ctx) return;

  if (charts.distribution) charts.distribution.destroy();

  const totalOccupied = zones.occupied.reduce((a, b) => a + b, 0);
  const totalAvailable = zones.available.reduce((a, b) => a + b, 0);

  charts.distribution = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: ["Occupied (Active)", "Available (Ready)"],
      datasets: [
        {
          data: [totalOccupied, totalAvailable],
          backgroundColor: ["#DC2626", "#059669"],
          hoverOffset: 6
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" }
      },
      cutout: "65%"
    }
  });
}

// 4. Urban Parking Utilization Trends (Line Chart)
function renderTrendChart(trends) {
  const ctx = document.getElementById("chart-trend");
  if (!ctx) return;

  if (charts.trend) charts.trend.destroy();

  charts.trend = new Chart(ctx, {
    type: "line",
    data: {
      labels: trends.hours,
      datasets: [
        {
          label: "Average Occupancy % (Urban Rush Profile)",
          data: trends.utilization,
          borderColor: "#028090",
          backgroundColor: "rgba(0, 168, 150, 0.15)",
          fill: true,
          tension: 0.35,
          pointRadius: 5,
          pointBackgroundColor: "#0B192C"
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" }
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          title: { display: true, text: "Occupancy Percentage (%)" }
        }
      }
    }
  });
}
