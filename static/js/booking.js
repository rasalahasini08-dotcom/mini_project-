/**
 * booking.js - Interactive Slot Grid, Concurrency-Safe Booking, and Real-Time Cancellation.
 */

let currentZoneId = null;
let currentZonePricing = null;

// Initialize booking page
document.addEventListener("DOMContentLoaded", () => {
  const zoneSelect = document.getElementById("zone-select");
  if (zoneSelect) {
    currentZoneId = parseInt(zoneSelect.value, 10);
    loadZoneSlots(currentZoneId);

    zoneSelect.addEventListener("change", (e) => {
      currentZoneId = parseInt(e.target.value, 10);
      loadZoneSlots(currentZoneId);
    });
  }

  // Setup manual booking form
  const bookingForm = document.getElementById("booking-form");
  if (bookingForm) {
    bookingForm.addEventListener("submit", handleManualBookingSubmit);
  }

  // Setup auto-allocate form
  const autoForm = document.getElementById("auto-allocate-form");
  if (autoForm) {
    autoForm.addEventListener("submit", handleAutoAllocateSubmit);
  }

  // Setup cancellation search form
  const cancelForm = document.getElementById("cancel-form");
  if (cancelForm) {
    cancelForm.addEventListener("submit", handleCancelBookingSubmit);
  }

  // Modal close handlers
  const btnCloseModal = document.getElementById("btn-close-modal");
  const btnCancelModal = document.getElementById("btn-cancel-modal");
  if (btnCloseModal) btnCloseModal.addEventListener("click", closeBookingModal);
  if (btnCancelModal) btnCancelModal.addEventListener("click", closeBookingModal);

  const confirmModalClose = document.getElementById("btn-close-confirm-modal");
  if (confirmModalClose) {
    confirmModalClose.addEventListener("click", () => {
      document.getElementById("confirmation-modal").classList.remove("active");
    });
  }
});

// Load slots and pricing for the chosen zone
async function loadZoneSlots(zoneId) {
  const grid = document.getElementById("slots-grid");
  if (!grid) return;

  grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 2rem; color: #64748B;">Fetching live bay state from database...</div>';

  try {
    const res = await fetch(`/api/zones/${zoneId}/slots`);
    const json = await res.json();

    if (!json.success) {
      grid.innerHTML = `<div style="grid-column: 1/-1; color: #DC2626; text-align: center;">${json.message || "Failed to load slots"}</div>`;
      return;
    }

    currentZonePricing = json.pricing;
    updateZonePricingBadge(json.pricing);

    const slots = json.slots;
    if (slots.length === 0) {
      grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #64748B;">No parking slots found in this zone.</div>';
      return;
    }

    grid.innerHTML = "";
    slots.forEach(slot => {
      const card = createSlotElement(slot);
      grid.appendChild(card);
    });

  } catch (err) {
    grid.innerHTML = `<div style="grid-column: 1/-1; color: #DC2626; text-align: center;">Error connecting to allocation server: ${err.message}</div>`;
  }
}

// Create individual slot card element
function createSlotElement(slot) {
  const card = document.createElement("div");
  const statusClass = slot.status.toLowerCase();
  card.className = `slot-card ${statusClass}`;
  card.dataset.slotId = slot.id;
  card.dataset.slotNumber = slot.slot_number;
  card.dataset.slotType = slot.slot_type;

  let typeIcon = "🚗";
  if (slot.slot_type === "EV Charging") typeIcon = "⚡";
  else if (slot.slot_type === "Accessible") typeIcon = "♿";

  card.innerHTML = `
    <div>
      <div class="slot-num">${slot.slot_number}</div>
      <div class="slot-type-icon" title="${slot.slot_type}">${typeIcon} <span style="font-size: 0.72rem; color: #64748B;">${slot.slot_type}</span></div>
    </div>
    <div>
      <span class="slot-status-text">${slot.status}</span>
    </div>
  `;

  if (slot.status === "AVAILABLE") {
    card.title = `Click to reserve slot ${slot.slot_number}`;
    card.addEventListener("click", () => openBookingModal(slot));
  } else if (slot.status === "OCCUPIED") {
    card.title = `Slot ${slot.slot_number} is occupied.`;
  } else {
    card.title = `Slot ${slot.slot_number} is under maintenance.`;
  }

  return card;
}

// Update pricing badge on booking page
function updateZonePricingBadge(pricing) {
  const badgeContainer = document.getElementById("zone-pricing-banner");
  if (!badgeContainer) return;

  badgeContainer.innerHTML = `
    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
      <div>
        <span style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; color: #64748B;">Zone Tariff:</span>
        <span style="font-size: 1.25rem; font-weight: 800; color: #0B192C; margin-left: 0.5rem;">₹${pricing.effective_rate} / hr</span>
        <span class="badge ${pricing.badge_class}" style="margin-left: 0.5rem;">${pricing.demand_level} (${pricing.multiplier}x)</span>
      </div>
      <div style="font-size: 0.82rem; color: #64748B;">
        Occupancy: <strong>${pricing.occupied_slots}/${pricing.total_slots}</strong> (${pricing.occupancy_percentage}%) &bull; Base: ₹${pricing.base_rate}/hr
      </div>
    </div>
  `;
}

// Open booking modal for a selected slot
function openBookingModal(slot) {
  const modal = document.getElementById("booking-modal");
  const slotIdInput = document.getElementById("form-slot-id");
  const modalSlotTitle = document.getElementById("modal-slot-id");
  const ratePreview = document.getElementById("modal-rate-preview");
  const multPreview = document.getElementById("modal-mult-preview");

  if (!modal) return;

  slotIdInput.value = slot.id;
  modalSlotTitle.textContent = `${slot.slot_number} (${slot.slot_type})`;

  if (currentZonePricing) {
    ratePreview.textContent = `₹${currentZonePricing.effective_rate} / hr`;
    multPreview.textContent = `${currentZonePricing.multiplier}x (${currentZonePricing.demand_level})`;
  }

  modal.classList.add("active");
}

function closeBookingModal() {
  const modal = document.getElementById("booking-modal");
  if (modal) modal.classList.remove("active");
}

// Handle manual booking submit
async function handleManualBookingSubmit(e) {
  e.preventDefault();

  const slotId = document.getElementById("form-slot-id").value;
  const driverName = document.getElementById("form-driver-name").value.trim();
  const vehicleNo = document.getElementById("form-vehicle-no").value.trim();
  const contactNo = document.getElementById("form-contact-no") ? document.getElementById("form-contact-no").value.trim() : null;

  const submitBtn = document.getElementById("btn-submit-booking");
  const submitText = document.getElementById("btn-submit-text");

  if (submitBtn) submitBtn.disabled = true;
  if (submitText) submitText.textContent = "Processing Transaction...";

  try {
    const res = await fetch("/api/book", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slot_id: parseInt(slotId, 10),
        driver_name: driverName,
        vehicle_number: vehicleNo,
        contact_number: contactNo
      })
    });

    const json = await res.json();

    if (res.status === 201 && json.success) {
      closeBookingModal();
      showToast("Slot allocated successfully! Lock acquired & booking committed.", "success");
      displayConfirmation(json.booking);
      loadZoneSlots(currentZoneId);
      updateGlobalMetrics();
    } else if (res.status === 409) {
      showToast(`Race Condition Prevented: ${json.message}`, "error");
      loadZoneSlots(currentZoneId); // Refresh to show newly occupied slot
    } else {
      showToast(`Booking Failed: ${json.message || "Unknown error"}`, "error");
    }
  } catch (err) {
    showToast(`Network or server error: ${err.message}`, "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (submitText) submitText.textContent = "Confirm Booking";
  }
}

// Handle automatic allocation submit
async function handleAutoAllocateSubmit(e) {
  e.preventDefault();

  const zoneId = document.getElementById("auto-zone-select").value;
  const slotType = document.getElementById("auto-slot-type").value;
  const driverName = document.getElementById("auto-driver-name").value.trim();
  const vehicleNo = document.getElementById("auto-vehicle-no").value.trim();
  const contactNo = document.getElementById("auto-contact-no") ? document.getElementById("auto-contact-no").value.trim() : null;

  const submitBtn = document.getElementById("btn-auto-submit");
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Allocating Optimal Slot...";
  }

  try {
    const res = await fetch("/api/auto-allocate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        zone_id: parseInt(zoneId, 10),
        slot_type: slotType,
        driver_name: driverName,
        vehicle_number: vehicleNo,
        contact_number: contactNo
      })
    });

    const json = await res.json();

    if (res.status === 201 && json.success) {
      showToast("Optimal slot automatically allocated and locked!", "success");
      displayConfirmation(json.booking);
      if (currentZoneId === parseInt(zoneId, 10)) {
        loadZoneSlots(currentZoneId);
      }
      updateGlobalMetrics();
    } else if (res.status === 409) {
      showToast(`Allocation Notice: ${json.message}`, "warning");
    } else {
      showToast(`Auto-Allocation Error: ${json.message || "Failed"}`, "error");
    }
  } catch (err) {
    showToast(`Request failed: ${err.message}`, "error");
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = "Auto-Allocate Best Slot";
    }
  }
}

// Display booking confirmation card/modal
function displayConfirmation(bkg) {
  const modal = document.getElementById("confirmation-modal");
  if (!modal) return;

  document.getElementById("confirm-ref").textContent = bkg.booking_reference;
  document.getElementById("confirm-slot").textContent = `${bkg.slot_number} (${bkg.zone_name || bkg.zone_code})`;
  document.getElementById("confirm-driver").textContent = bkg.driver_name;
  document.getElementById("confirm-vehicle").textContent = bkg.vehicle_number;
  document.getElementById("confirm-rate").textContent = `₹${bkg.hourly_rate} / hr (${bkg.multiplier}x Surge)`;
  document.getElementById("confirm-time").textContent = new Date(bkg.booked_at).toLocaleString();

  // Setup one-click cancel button on confirmation card
  const btnCancelActive = document.getElementById("btn-cancel-from-confirm");
  if (btnCancelActive) {
    btnCancelActive.onclick = () => {
      cancelBooking(bkg.booking_reference, () => {
        modal.classList.remove("active");
      });
    };
  }

  modal.classList.add("active");
}

// Handle cancellation search form
async function handleCancelBookingSubmit(e) {
  e.preventDefault();
  const refInput = document.getElementById("cancel-ref-input");
  const ref = refInput.value.trim().toUpperCase();

  if (!ref) {
    showToast("Please enter a valid Booking Reference.", "warning");
    return;
  }

  cancelBooking(ref, () => {
    refInput.value = "";
  });
}

// General cancel booking routine
async function cancelBooking(reference, onSuccessCallback) {
  if (!confirm(`Are you sure you want to cancel booking ${reference} and release the slot?`)) {
    return;
  }

  try {
    const res = await fetch("/api/cancel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ booking_reference: reference })
    });

    const json = await res.json();

    if (json.success) {
      showToast(json.message, "success");
      if (onSuccessCallback) onSuccessCallback();
      if (currentZoneId) loadZoneSlots(currentZoneId);
      updateGlobalMetrics();
    } else {
      showToast(`Cancellation Rejected: ${json.message}`, "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}
