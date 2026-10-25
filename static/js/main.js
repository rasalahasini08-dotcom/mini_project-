/**
 * main.js - Global utilities, status indicators, and toast notification manager.
 */

// Toast notification helper
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  
  const icon = type === "success" ? "✅" : (type === "error" || type === "danger" ? "⚠️" : "ℹ️");
  toast.innerHTML = `
    <span style="font-size: 1.1rem;">${icon}</span>
    <div style="flex: 1;">${message}</div>
    <button style="background: none; border: none; cursor: pointer; color: #94A3B8; font-size: 1rem;" onclick="this.parentElement.remove();">&times;</button>
  `;

  container.appendChild(toast);

  // Auto-remove after 4.5 seconds
  setTimeout(() => {
    if (toast.parentElement) {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => toast.remove(), 300);
    }
  }, 4500);
}

// Global live metrics updater
async function updateGlobalMetrics() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const json = await res.json();
    if (!json.success || !json.data) return;

    const data = json.data;
    
    // Update ribbon metrics if present on page
    const totalEl = document.getElementById("metric-total");
    const availEl = document.getElementById("metric-available");
    const occEl = document.getElementById("metric-occupied");
    const pctEl = document.getElementById("metric-occupancy");
    const barEl = document.getElementById("occupancy-bar");

    if (totalEl) totalEl.textContent = data.total_capacity;
    if (availEl) availEl.textContent = data.available_slots;
    if (occEl) occEl.textContent = data.occupied_slots;
    if (pctEl) pctEl.textContent = `${data.overall_occupancy_percentage}%`;
    if (barEl) {
      barEl.style.width = `${data.overall_occupancy_percentage}%`;
      barEl.className = "progress-bar-fill";
      if (data.overall_occupancy_percentage >= 85) {
        barEl.classList.add("danger");
      } else if (data.overall_occupancy_percentage >= 50) {
        barEl.classList.add("warning");
      }
    }
  } catch (err) {
    console.debug("Live metrics poll failed:", err);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Setup manual refresh buttons if present
  const refreshBtn = document.getElementById("btn-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      updateGlobalMetrics();
      showToast("Dashboard refreshed from database.", "info");
    });
  }

  // Periodic polling every 15 seconds
  setInterval(updateGlobalMetrics, 15000);
});
