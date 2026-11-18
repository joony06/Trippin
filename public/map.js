// 트립핀 지도 (Leaflet + OpenStreetMap)
// 버전 기록
// v0.1 (2026-11-18) 장소 마커 표시, 순위 번호 마커, 마커 클릭 시 상세로 이동(유입 경로 map)
// 네이버 지도로 바꿀 때는 이 파일만 교체하면 된다. 데이터는 #map-data(JSON)에서 읽는다.
(function () {
  var el = document.getElementById("map");
  var dataEl = document.getElementById("map-data");
  if (!el || !dataEl || typeof L === "undefined") return;

  var points = JSON.parse(dataEl.textContent || "[]");
  var origin = [36.3256, 127.4213]; // 대전 중구청 앞 (MVP 고정 위치)
  var map = L.map(el).setView(origin, 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);

  L.circleMarker(origin, { radius: 7, color: "#1E5BD8", fillColor: "#2F86FF", fillOpacity: 0.9 })
    .addTo(map).bindTooltip("📍");

  var keep = new URLSearchParams(window.location.search);
  keep.delete("src");
  var bounds = [origin];
  points.forEach(function (p) {
    var label = p.rank ? String(p.rank) : "•";
    var icon = L.divIcon({ className: "pin-wrap", html: '<span class="pin">' + label + "</span>", iconSize: [28, 28] });
    var params = new URLSearchParams(keep);
    params.set("src", p.src || "map");
    var href = "/place/" + p.id + "?" + params.toString();
    L.marker([p.lat, p.lng], { icon: icon }).addTo(map)
      .bindPopup('<a href="' + href + '">' + p.name.replace(/</g, "&lt;") + "</a>");
    bounds.push([p.lat, p.lng]);
  });
  if (points.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
})();
