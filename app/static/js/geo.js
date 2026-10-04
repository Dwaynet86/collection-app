// Shared map helpers (offline: the base map is a bundled GeoJSON of country outlines).
window.Geo = (function () {
  const css = (name, fallback) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

  function pinIcon() {
    return L.divIcon({ className: "geo-pin", html: "<span></span>", iconSize: [24, 32], iconAnchor: [12, 32], popupAnchor: [0, -30] });
  }

  // Creates a Leaflet map showing country outlines. `el.dataset.countries` is the outlines URL.
  function createMap(el, options) {
    const opts = options || {};
    const map = L.map(el, {
      preferCanvas: true, minZoom: 1, maxZoom: 9, zoomSnap: 0.5, worldCopyJump: false,
      maxBounds: [[-85, -180], [85, 180]], maxBoundsViscosity: 1.0,
    });
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution("Map: Natural Earth · Places: GeoNames");
    el.style.background = css("--ocean", "#cfe3ee");
    map.setView([25, 10], 2);

    fetch(el.dataset.countries)
      .then((r) => r.json())
      .then((data) => {
        const layer = L.geoJSON(data, {
          interactive: !!opts.hoverNames,
          style: { color: css("--border-map", "#9aa7b3"), weight: 0.7, fillColor: css("--land", "#f1ede2"), fillOpacity: 1 },
          onEachFeature: (feature, l) => {
            if (opts.hoverNames) l.bindTooltip(document.createTextNode(feature.properties.n).textContent, { sticky: true });
          },
        });
        layer.addTo(map);
        layer.bringToBack();
      })
      .catch(() => { el.dataset.outlinesFailed = "1"; });
    return map;
  }

  return { createMap, pinIcon };
})();
