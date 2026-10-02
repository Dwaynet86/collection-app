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
