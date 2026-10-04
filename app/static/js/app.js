/* Small progressive enhancements. No dependencies. */

// Open / close confirmation dialogs.
document.querySelectorAll("[data-open-dialog]").forEach((btn) => {
  btn.addEventListener("click", () =>
    document.getElementById(btn.dataset.openDialog)?.showModal());
});
document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
  btn.addEventListener("click", () => btn.closest("dialog").close());
});

// Submit the sort form as soon as the selection changes.
document.querySelectorAll("[data-autosubmit]").forEach((el) => {
  el.addEventListener("change", () => el.form.submit());
});

// Collection switcher: navigate when a collection is chosen.
document.querySelectorAll("[data-nav]").forEach((el) => {
  el.addEventListener("change", () => { window.location.href = el.value; });
});

// Live preview of the chosen image on the item form.
const fileInput = document.getElementById("image");
if (fileInput) {
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (!file) return;
    const img = document.getElementById("preview-img");
    img.src = URL.createObjectURL(file);
    img.hidden = false;
    document.getElementById("preview-empty")?.remove();
  });
}

// Clicking an existing tag on the item form appends it to the tags field.
const tagsInput = document.getElementById("tags");
document.querySelectorAll("[data-add-tag]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tags = tagsInput.value.split(",").map((t) => t.trim()).filter(Boolean);
    const tag = btn.dataset.addTag;
    if (!tags.some((t) => t.toLowerCase() === tag.toLowerCase())) tags.push(tag);
    tagsInput.value = tags.join(", ");
    tagsInput.focus();
  });
});

// "Take photo": open the phone camera, then hand the shot to the real upload field.
const cameraBtn = document.getElementById("camera-btn");
const cameraInput = document.getElementById("camera");
if (cameraBtn && cameraInput && fileInput) {
  cameraBtn.addEventListener("click", () => cameraInput.click());
  cameraInput.addEventListener("change", () => {
    if (!cameraInput.files.length) return;
    fileInput.files = cameraInput.files;
    fileInput.dispatchEvent(new Event("change"));
  });
}

// Gallery view: thumbnail size slider + show/hide details (remembered per browser).
const sizeInput = document.getElementById("tile-size");
const detailsInput = document.getElementById("show-details");
const remember = (key, value) => { try { localStorage.setItem(key, value); } catch (e) {} };
const recall = (key) => { try { return localStorage.getItem(key); } catch (e) { return null; } };
if (sizeInput) {
  sizeInput.value = recall("collection.tileSize") || sizeInput.value;
  sizeInput.addEventListener("input", () => {
    document.documentElement.style.setProperty("--tile-min", `${sizeInput.value}px`);
    remember("collection.tileSize", sizeInput.value);
  });
}
if (detailsInput) {
  detailsInput.checked = recall("collection.showDetails") !== "0";
  detailsInput.addEventListener("change", () => {
    document.documentElement.classList.toggle("hide-details", !detailsInput.checked);
    remember("collection.showDetails", detailsInput.checked ? "1" : "0");
  });
}

// Item form: choosing a trip fills in the date acquired with the trip's start date.
// A date typed by the user is never overwritten; only an empty field or a previous auto-fill.
const tripSelect = document.getElementById("trip_id");
const dateInput = document.getElementById("date_acquired");
if (tripSelect && dateInput) {
  const hint = document.getElementById("trip-hint");
  let lastAuto = "";
  const showHint = () => {
    const opt = tripSelect.selectedOptions[0];
    hint.textContent = opt && opt.dataset.dates ? `Trip dates: ${opt.dataset.dates}.` : "";
  };
  tripSelect.addEventListener("change", () => {
    showHint();
    const start = tripSelect.selectedOptions[0]?.dataset.start || "";
    if (dateInput.value === "" || dateInput.value === lastAuto) {
      dateInput.value = start;
      lastAuto = start;
    }
  });
  showHint();
}

// Background removal takes a few seconds: show progress and prevent double submits.
const bgBox = document.getElementById("remove_background");
if (bgBox && bgBox.form) {
  bgBox.form.addEventListener("submit", () => {
    const btn = bgBox.form.querySelector('button[type="submit"]');
    if (bgBox.checked && btn) {
      btn.textContent = "Removing background…";
      setTimeout(() => { btn.disabled = true; }, 0);
    }
  });
}
