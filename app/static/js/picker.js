// Item form: pick a location on the map (click, drag, search, or type coordinates).
(function () {
  const box = document.getElementById("geo-picker");
  if (!box || !window.L || !window.Geo) return;

  const latIn = document.getElementById("latitude");
  const lonIn = document.getElementById("longitude");
  const locIn = document.getElementById("location_acquired");
  const mapEl = document.getElementById("geo-map");
  const searchIn = document.getElementById("geo-search");
  const results = document.getElementById("geo-results");
  mapEl.dataset.countries = box.dataset.countries;

  let map = null, marker = null, lastAuto = "";

  const valid = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  const round5 = (n) => Math.round(n * 1e5) / 1e5;
  const readCoords = () => {
    const lat = parseFloat(latIn.value), lon = parseFloat(lonIn.value);
    return valid(lat, lon) ? [lat, lon] : null;
  };

  function placeMarker(lat, lon, pan) {
    if (!map) return;
    if (!marker) {
      marker = L.marker([lat, lon], { icon: Geo.pinIcon(), draggable: true }).addTo(map);
      marker.on("dragend", () => { const p = marker.getLatLng(); setPin(p.lat, p.lng, false); });
    } else {
      marker.setLatLng([lat, lon]);
    }
    if (pan) map.setView([lat, lon], Math.max(map.getZoom(), 5));
  }

  function setPin(lat, lon, pan) {
    lat = round5(lat); lon = round5(lon);
    latIn.value = lat; lonIn.value = lon;
    placeMarker(lat, lon, pan);
  }

  function clearPin() {
    latIn.value = ""; lonIn.value = "";
    if (marker) { marker.remove(); marker = null; }
  }

  function initMap() {
    if (map) { map.invalidateSize(); return; }
    map = Geo.createMap(mapEl);
    map.on("click", (e) => setPin(e.latlng.lat, e.latlng.lng, false));
    const c = readCoords();
    if (c) placeMarker(c[0], c[1], true);
  }

  // The map can't measure itself inside a closed <details>, so build it on first open.
  box.addEventListener("toggle", () => { if (box.open) initMap(); });
  if (box.open) initMap();

  // Typing coordinates (or pasting "38.72, -9.14" into either box) moves the pin.
  const pair = /^\s*(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)\s*$/;
  const fromInputs = () => {
    const m = pair.exec(latIn.value);
    if (m) { latIn.value = m[1]; lonIn.value = m[2]; }
    const c = readCoords();
    if (c) placeMarker(c[0], c[1], true);
  };
  latIn.addEventListener("change", fromInputs);
  lonIn.addEventListener("change", fromInputs);
  document.getElementById("geo-clear").addEventListener("click", clearPin);

  const locate = document.getElementById("geo-locate");
  if (window.isSecureContext && navigator.geolocation) {   // browsers only allow this over HTTPS/localhost
    locate.hidden = false;
    locate.addEventListener("click", () => {
      navigator.geolocation.getCurrentPosition((pos) => setPin(pos.coords.latitude, pos.coords.longitude, true));
    });
  }

  // ---- search (local, offline) ----
  let timer = null, controller = null, items = [], active = -1;

  function closeResults() { results.hidden = true; searchIn.setAttribute("aria-expanded", "false"); active = -1; }

  function choose(r) {
    setPin(r.lat, r.lon, true);
    // Fill the location text only if it's empty or still holds the last auto-filled value.
    if (locIn.value.trim() === "" || locIn.value === lastAuto) { locIn.value = r.label; lastAuto = r.label; }
    searchIn.value = "";
    closeResults();
  }

  function render() {
    results.replaceChildren();
    items.forEach((r, i) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.textContent = r.label;
      if (r.kind === "country") li.classList.add("is-country");
      li.addEventListener("mousedown", (e) => { e.preventDefault(); choose(r); });
      results.appendChild(li);
    });
    results.hidden = items.length === 0;
    searchIn.setAttribute("aria-expanded", String(items.length > 0));
  }

  function highlight(i) {
    active = i;
    [...results.children].forEach((li, n) => li.classList.toggle("active", n === i));
  }

  searchIn.addEventListener("input", () => {
    clearTimeout(timer);
    const q = searchIn.value.trim();
    if (q.length < 2) { items = []; render(); return; }
    timer = setTimeout(async () => {
      if (controller) controller.abort();
      controller = new AbortController();
      try {
        const res = await fetch(`${box.dataset.searchUrl}?q=${encodeURIComponent(q)}`, { signal: controller.signal });
        items = res.ok ? await res.json() : [];
        render();
      } catch (e) { /* aborted or offline: keep what we have */ }
    }, 150);
  });

  searchIn.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {            // never submit the item form from the search box
      e.preventDefault();
      if (items.length) choose(items[Math.max(active, 0)]);
    } else if (e.key === "ArrowDown" && items.length) { e.preventDefault(); highlight((active + 1) % items.length); }
    else if (e.key === "ArrowUp" && items.length) { e.preventDefault(); highlight((active - 1 + items.length) % items.length); }
    else if (e.key === "Escape") closeResults();
  });
  searchIn.addEventListener("blur", () => setTimeout(closeResults, 100));
})();
