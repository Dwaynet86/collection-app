// Collection map: one pin per item with coordinates, filtered by search / tag / trip.
(function () {
  const root = document.getElementById("map-page");
  if (!root || !window.L || !window.Geo) return;

  const mapEl = root.querySelector("#geo-map");
  mapEl.dataset.countries = root.dataset.countries;
  const form = root.querySelector(".map-filters");
  const status = root.querySelector("#map-status");
  const focusId = parseInt(root.dataset.focus, 10) || null;

  const map = Geo.createMap(mapEl, { hoverNames: true });
  const cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45 });
  map.addLayer(cluster);

  let markers = new Map(), request = 0, firstLoad = true, timer = null;

  // Popups are built with DOM calls (textContent), never HTML strings, so item names can't inject markup.
  function popupFor(p) {
    const wrap = document.createElement("div");
    wrap.className = "pin-popup";
    if (p.thumb) {
      const img = document.createElement("img");
      img.src = p.thumb; img.alt = ""; img.loading = "lazy";
      wrap.appendChild(img);
    }
    const a = document.createElement("a");
    a.href = p.url; a.textContent = p.name; a.className = "pin-name";
    wrap.appendChild(a);
    if (p.where) {
      const where = document.createElement("div");
      where.className = "pin-where"; where.textContent = p.where;
      wrap.appendChild(where);
    }
    return wrap;
  }

  function describe(data) {
    const parts = [`${data.pins.length} pinned`];
    if (data.unpinned) parts.push(`${data.unpinned} without a pin`);
    if (data.truncated) parts.push("showing the first 5,000");
    return `${data.matching} item${data.matching === 1 ? "" : "s"} match — ${parts.join(", ")}.`;
  }

  async function load() {
    const params = new URLSearchParams(new FormData(form));
    for (const [k, v] of [...params]) if (!v) params.delete(k);
    const qs = params.toString();
    history.replaceState(null, "", qs ? `?${qs}` : location.pathname);

    const mine = ++request;
    let data;
    try {
      const res = await fetch(`${root.dataset.pinsUrl}${qs ? "?" + qs : ""}`, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(res.status);
      data = await res.json();
    } catch (e) {
      status.textContent = "Couldn't load the pins. Check the connection to the server and try again.";
      return;
    }
    if (mine !== request) return;       // a newer filter change superseded this response

    cluster.clearLayers();
    markers = new Map();
    const layers = data.pins.map((p) => {
      const m = L.marker([p.lat, p.lon], { icon: Geo.pinIcon(), title: p.name });
      m.bindPopup(popupFor(p));
      markers.set(p.id, m);
      return m;
    });
    cluster.addLayers(layers);
    status.textContent = describe(data);

    const target = firstLoad && focusId ? markers.get(focusId) : null;
    if (target) {
      map.setView(target.getLatLng(), 7);
      cluster.zoomToShowLayer(target, () => target.openPopup());
    } else if (layers.length) {
      map.fitBounds(cluster.getBounds().pad(0.25), { maxZoom: 6 });
    } else {
      map.setView([25, 10], 2);
    }
    firstLoad = false;
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); load(); });
  form.querySelectorAll("select").forEach((s) => s.addEventListener("change", load));
  form.querySelector('input[name="q"]').addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(load, 250); });
  load();
})();
