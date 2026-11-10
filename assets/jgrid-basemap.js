/* Shared CARTO Basemaps loader. The deployment supplies a restricted public key. */
(function () {
  "use strict";
  window.addJGridBasemap = function (map, style, opacity) {
    let notice = null;
    function showError() {
      if (notice) return;
      notice = L.control({ position: "bottomleft" });
      notice.onAdd = function () {
        const node = L.DomUtil.create("div", "info-box");
        node.textContent = "Basemap unavailable / 背景地図を読み込めません";
        return node;
      };
      notice.addTo(map);
    }
    return fetch("../carto-config.json", { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("Basemap configuration unavailable");
        return response.json();
      })
      .then(function (config) {
        if (typeof config.basemapsKey !== "string" || !config.basemapsKey.trim()) {
          throw new Error("Basemap configuration unavailable");
        }
        const layer = L.tileLayer(
          "https://{s}.basemaps.cartocdn.com/" + style + "/{z}/{x}/{y}{r}.png?key=" +
            encodeURIComponent(config.basemapsKey.trim()),
          {
            subdomains: "abcd",
            opacity: opacity,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attribution/">CARTO</a>'
          }
        );
        layer.on("tileerror", showError);
        layer.addTo(map);
      })
      .catch(showError);
  };
})();

