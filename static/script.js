/**
 * script.js - Frontend Controller for Urban Parking Allocator
 * Handles dashboard data synchronization, modal interactions, booking submissions,
 * cancellations, dynamic pricing visualizations, and toast alerts.
 */

document.addEventListener("DOMContentLoaded", () => {
    // --- State & DOM References ---
    let currentPricing = { hourly_rate: 50 };
    let isSubmitting = false;

    const metricTotal = document.getElementById("metric-total");
    const metricAvailable = document.getElementById("metric-available");
    const metricOccupied = document.getElementById("metric-occupied");
    const metricOccupancy = document.getElementById("metric-occupancy");
    const metricOccupancyDesc = document.getElementById("metric-occupancy-desc");
    const occupancyBar = document.getElementById("occupancy-bar");
    const metricPrice = document.getElementById("metric-price");
    const surgeBadge = document.getElementById("surge-badge");
    const surgeDescription = document.getElementById("surge-description");

    const tierStandard = document.getElementById("tier-standard");
    const tierModerate = document.getElementById("tier-moderate");
    const tierPeak = document.getElementById("tier-peak");

    const slotsGrid = document.getElementById("slots-grid");
    const historyTbody = document.getElementById("history-tbody");
    const historyCount = document.getElementById("history-count");
    const btnRefresh = document.getElementById("btn-refresh");

    // Modal elements
    const bookingModal = document.getElementById("booking-modal");
    const modalSlotId = document.getElementById("modal-slot-id");
    const formSlotId = document.getElementById("form-slot-id");
    const formUserName = document.getElementById("form-user-name");
    const formVehicleNo = document.getElementById("form-vehicle-no");
    const modalRatePreview = document.getElementById("modal-rate-preview");
    const bookingForm = document.getElementById("booking-form");
    const btnCloseModal = document.getElementById("btn-close-modal");
    const btnCancelModal = document.getElementById("btn-cancel-modal");
    const btnSubmitBooking = document.getElementById("btn-submit-booking");
    const btnSubmitText = document.getElementById("btn-submit-text");

    const toastContainer = document.getElementById("toast-container");

    // --- Toast Notifications ---
    function showToast(message, type = "info") {
        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        
        const iconMap = {
            success: "✅",
            error: "❌",
            info: "ℹ️"
        };

        toast.innerHTML = `
            <span>${iconMap[type] || "ℹ️"}</span>
            <div style="flex:1;">${escapeHtml(message)}</div>
        `;
        toastContainer.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateY(10px)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    }

    // --- Utility: HTML Escaping ---
    function escapeHtml(str) {
        if (!str) return "";
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    // --- Utility: Format Timestamp ---
    function formatTime(isoStr) {
        if (!isoStr) return "--";
        try {
            const date = new Date(isoStr);
            return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + 
                   " (" + date.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ")";
        } catch {
            return isoStr;
        }
    }

    // --- Dashboard Data Fetching ---
    async function loadDashboard() {
        btnRefresh.classList.add("disabled");
        try {
            // Fetch status, slots, and history in parallel
            const [statusRes, slotsRes, historyRes] = await Promise.all([
                fetch("/api/status"),
                fetch("/api/slots"),
                fetch("/api/history?limit=15")
            ]);

            const statusJson = await statusRes.json();
            const slotsJson = await slotsRes.json();
            const historyJson = await historyRes.json();

            if (statusJson.success) {
                renderStatus(statusJson.data);
            }
            if (slotsJson.success) {
                renderSlots(slotsJson.data);
            }
            if (historyJson.success) {
                renderHistory(historyJson.data);
            }
        } catch (err) {
            console.error("Dashboard refresh error:", err);
            showToast("Failed to connect to backend server. Retrying...", "error");
        } finally {
            btnRefresh.classList.remove("disabled");
        }
    }

    // --- Render Top Metrics & Surge Pricing ---
    function renderStatus(stats) {
        metricTotal.textContent = stats.total_slots;
        metricAvailable.textContent = stats.available_slots;
        metricOccupied.textContent = stats.occupied_slots;

        const occupancyPct = stats.occupancy_percentage;
        metricOccupancy.textContent = `${occupancyPct}%`;
        occupancyBar.style.width = `${occupancyPct}%`;

        // Bar color adjustments based on occupancy
        if (occupancyPct >= 80) {
            occupancyBar.style.backgroundColor = "var(--red-500)";
            metricOccupancyDesc.textContent = "Critical occupancy (Peak Surge)";
        } else if (occupancyPct >= 50) {
            occupancyBar.style.backgroundColor = "var(--amber-500)";
            metricOccupancyDesc.textContent = "Elevated occupancy (Moderate Surge)";
        } else {
            occupancyBar.style.backgroundColor = "var(--green-500)";
            metricOccupancyDesc.textContent = "Normal occupancy (Standard Rate)";
        }

        const pricing = stats.pricing;
        currentPricing = pricing;
        metricPrice.textContent = `₹${pricing.hourly_rate}`;
        surgeBadge.textContent = pricing.tier_name;
        surgeBadge.className = `badge badge-${pricing.badge_variant}`;
        surgeDescription.textContent = pricing.description;

        // Highlight active surge tier card
        [tierStandard, tierModerate, tierPeak].forEach(card => card.classList.remove("active-tier"));
        if (pricing.tier_key === "STANDARD") {
            tierStandard.classList.add("active-tier");
        } else if (pricing.tier_key === "MODERATE") {
            tierModerate.classList.add("active-tier");
        } else if (pricing.tier_key === "PEAK") {
            tierPeak.classList.add("active-tier");
        }
    }

    // --- Render 12 Parking Slot Cards ---
    function renderSlots(slots) {
        slotsGrid.innerHTML = "";
        if (!slots || slots.length === 0) {
            slotsGrid.innerHTML = `<div class="loading-state">No parking slots initialized.</div>`;
            return;
        }

        slots.forEach(slot => {
            const isAvail = slot.is_available;
            const card = document.createElement("div");
            card.className = `slot-card ${isAvail ? 'is-available' : 'is-occupied'}`;

            if (isAvail) {
                card.innerHTML = `
                    <div class="slot-header">
                        <span class="slot-id">${escapeHtml(slot.slot_id)}</span>
                        <span class="badge badge-success">Available</span>
                    </div>
                    <div class="slot-body">
                        <div class="slot-info-row">
                            <span>Status:</span>
                            <span class="slot-info-value text-success">Ready to Park</span>
                        </div>
                        <div class="slot-info-row">
                            <span>Current Rate:</span>
                            <span class="slot-info-value">₹${currentPricing.hourly_rate || 50}/hr</span>
                        </div>
                    </div>
                    <div class="slot-actions">
                        <button class="btn btn-primary btn-book" data-slot="${escapeHtml(slot.slot_id)}">
                            Book Slot
                        </button>
                    </div>
                `;
            } else {
                const b = slot.active_booking || {};
                card.innerHTML = `
                    <div class="slot-header">
                        <span class="slot-id">${escapeHtml(slot.slot_id)}</span>
                        <span class="badge badge-danger">Occupied</span>
                    </div>
                    <div class="slot-body">
                        <div class="slot-info-row">
                            <span>Vehicle:</span>
                            <span class="slot-info-value">${escapeHtml(b.vehicle_number || "Unknown")}</span>
                        </div>
                        <div class="slot-info-row">
                            <span>Driver:</span>
                            <span class="slot-info-value">${escapeHtml(b.user_name || "Unknown")}</span>
                        </div>
                        <div class="slot-info-row">
                            <span>Locked Rate:</span>
                            <span class="slot-info-value">₹${b.hourly_rate || "--"}/hr</span>
                        </div>
                    </div>
                    <div class="slot-actions">
                        <button class="btn btn-danger btn-cancel-bkg" data-booking="${escapeHtml(b.booking_id || '')}" data-slot="${escapeHtml(slot.slot_id)}">
                            Release Slot
                        </button>
                    </div>
                `;
            }

            slotsGrid.appendChild(card);
        });

        // Attach event listeners to slot action buttons
        document.querySelectorAll(".btn-book").forEach(btn => {
            btn.addEventListener("click", () => openBookingModal(btn.dataset.slot));
        });

        document.querySelectorAll(".btn-cancel-bkg").forEach(btn => {
            btn.addEventListener("click", () => handleCancelBooking(btn.dataset.booking, btn.dataset.slot));
        });
    }

    // --- Render Audit History Table ---
    function renderHistory(history) {
        historyTbody.innerHTML = "";
        historyCount.textContent = `${history.length} records`;

        if (!history || history.length === 0) {
            historyTbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">No booking activity recorded yet.</td></tr>`;
            return;
        }

        history.forEach(item => {
            const tr = document.createElement("tr");
            const isActive = item.status === "ACTIVE";
            const statusBadge = isActive
                ? `<span class="badge badge-success">ACTIVE</span>`
                : `<span class="badge badge-secondary">CANCELLED</span>`;

            const actionBtn = isActive
                ? `<button class="btn btn-danger btn-sm btn-table-cancel" data-booking="${escapeHtml(item.booking_id)}" data-slot="${escapeHtml(item.slot_id)}">Release</button>`
                : `<span class="text-muted">Released</span>`;

            tr.innerHTML = `
                <td><code>${escapeHtml(item.booking_id)}</code></td>
                <td><strong>${escapeHtml(item.slot_id)}</strong></td>
                <td>${escapeHtml(item.user_name)}</td>
                <td><code>${escapeHtml(item.vehicle_number)}</code></td>
                <td>₹${item.hourly_rate}/hr</td>
                <td>${formatTime(item.booked_at)}</td>
                <td>${statusBadge}</td>
                <td>${actionBtn}</td>
            `;
            historyTbody.appendChild(tr);
        });

        document.querySelectorAll(".btn-table-cancel").forEach(btn => {
            btn.addEventListener("click", () => handleCancelBooking(btn.dataset.booking, btn.dataset.slot));
        });
    }

    // --- Modal Management ---
    function openBookingModal(slotId) {
        modalSlotId.textContent = slotId;
        formSlotId.value = slotId;
        formUserName.value = "";
        formVehicleNo.value = "";
        modalRatePreview.textContent = `₹${currentPricing.hourly_rate || 50} / hr`;
        bookingModal.classList.add("is-open");
        formUserName.focus();
    }

    function closeModal() {
        bookingModal.classList.remove("is-open");
    }

    btnCloseModal.addEventListener("click", closeModal);
    btnCancelModal.addEventListener("click", closeModal);
    bookingModal.addEventListener("click", (e) => {
        if (e.target === bookingModal) closeModal();
    });

    // --- Booking Form Submission (Concurrency Safe Endpoint) ---
    bookingForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (isSubmitting) return;

        const slotId = formSlotId.value;
        const userName = formUserName.value.trim();
        const vehicleNo = formVehicleNo.value.trim().toUpperCase();

        if (!slotId || !userName || !vehicleNo) {
            showToast("Please complete all driver and vehicle details.", "error");
            return;
        }

        // Set UI loading state
        isSubmitting = true;
        btnSubmitBooking.disabled = true;
        btnSubmitBooking.classList.add("is-submitting");
        btnSubmitText.textContent = "Reserving...";

        try {
            const response = await fetch("/api/book", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    slot_id: slotId,
                    user_name: userName,
                    vehicle_number: vehicleNo
                })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                closeModal();
                showToast(`Success! Slot ${slotId} allocated (Booking ID: ${result.booking.booking_id}). Rate: ₹${result.booking.hourly_rate}/hr`, "success");
                await loadDashboard();
            } else {
                // Concurrency conflict (409) or validation failure (400)
                const errorMsg = result.message || "Could not complete booking request.";
                showToast(errorMsg, "error");
                // Immediately refresh dashboard to show updated real occupancy
                await loadDashboard();
            }
        } catch (err) {
            console.error("Booking error:", err);
            showToast("Network error communicating with the server.", "error");
        } finally {
            isSubmitting = false;
            btnSubmitBooking.disabled = false;
            btnSubmitBooking.classList.remove("is-submitting");
            btnSubmitText.textContent = "Confirm Booking";
        }
    });

    // --- Cancellation Handler ---
    async function handleCancelBooking(bookingId, slotId) {
        if (!bookingId) {
            showToast("Invalid booking reference.", "error");
            return;
        }

        const confirmed = confirm(`Are you sure you want to release slot ${slotId} and cancel booking ${bookingId}?`);
        if (!confirmed) return;

        try {
            const response = await fetch("/api/cancel", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ booking_id: bookingId })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                showToast(`Slot ${slotId} successfully released!`, "success");
                await loadDashboard();
            } else {
                showToast(result.message || "Failed to cancel booking.", "error");
                await loadDashboard();
            }
        } catch (err) {
            console.error("Cancellation error:", err);
            showToast("Network error cancelling booking.", "error");
        }
    }

    // --- Refresh Action & Periodic Sync ---
    btnRefresh.addEventListener("click", () => {
        loadDashboard();
        showToast("Dashboard refreshed from database.", "info");
    });

    // Initial Load
    loadDashboard();

    // Gentle sync every 10 seconds to keep multi-user dashboards updated
    setInterval(loadDashboard, 10000);
});
