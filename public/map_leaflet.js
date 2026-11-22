// 트립핀 지도 (Leaflet + OpenStreetMap): 네이버 지도가 안 될 때 사용
// 버전 기록
// v0.1 장소·순위 마커
// v0.2 출발점 표시
// v0.3 네이버 지도 폴백 파일로 분리
// v0.4 물방울 핀
// v0.5 서비스 지역 밖 어둡게, 축소 제한
// v0.6 최소 축소를 지도 칸 크기에 맞춤

window.TrippinMap = window.TrippinMap || {};
window.TrippinMap.leaflet = function (el, d) {
  if (typeof L === "undefined") return false;

  var map = L.map(el, { minZoom: d.MIN_ZOOM }).setView(d.origin, 14);
  d.withArea(function (a) {
    L.polygon([d.WORLD, a.junggu], {
      interactive: false, fillColor: d.MASK.fill, fillOpacity: d.MASK.fillOpacity,
      color: d.MASK.stroke, weight: d.MASK.weight, opacity: 0.9
    }).addTo(map);
    var b = a.daejeon_bounds;
    map.setMaxBounds(L.latLngBounds(b).pad(0.1));
    map.options.maxBoundsViscosity = 0.8;
    map.setMinZoom(d.fitZoom(el, b));
  });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);

  L.circleMarker(d.origin, { radius: 7, weight: 3, color: "#FFFFFF", fillColor: "#2F86FF", fillOpacity: 1 })
    .addTo(map).bindTooltip("📍");

  var bounds = [d.origin];
  d.points.forEach(function (p) {
    var size = d.pinSize(p);
    var icon = L.divIcon({ className: "pin-wrap", html: d.pinHtml(p), iconSize: [size, size], iconAnchor: d.pinAnchor(p) });
    L.marker([p.lat, p.lng], { icon: icon, zIndexOffset: d.isSelected(p) ? 1000 : 0 }).addTo(map)
      .bindPopup(d.popupHtml(p));
    bounds.push([p.lat, p.lng]);
  });
  if (d.points.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  return true;
};
