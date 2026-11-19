// 트립핀 지도 - Leaflet + OpenStreetMap (네이버 지도 폴백)
// 버전 기록
// v0.1 (2026-11-18) 장소 마커 표시, 순위 번호 마커, 마커 클릭 시 상세로 이동(유입 경로 map)  (원래 map.js)
// v0.2 (2026-11-19) 출발점을 #map-data의 origin에서 읽음 (현재 위치 반영)
// v0.3 (2026-11-19) 네이버 지도 폴백 파일로 분리. map.js가 키가 없거나 네이버 지도 로드에 실패하면 이 함수를 부른다
//
// TrippinMap.leaflet(el, d)  d: map.js가 만든 공통 데이터 (origin, points, label, href, isSelected, pinHtml, popupHtml)
window.TrippinMap = window.TrippinMap || {};
window.TrippinMap.leaflet = function (el, d) {
  if (typeof L === "undefined") return false;

  var map = L.map(el).setView(d.origin, 14);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors"
  }).addTo(map);

  // 출발점 (현재 위치 또는 대전 중구청 앞)
  L.circleMarker(d.origin, { radius: 7, color: "#1E5BD8", fillColor: "#2F86FF", fillOpacity: 0.9 })
    .addTo(map).bindTooltip("📍");

  var bounds = [d.origin];
  d.points.forEach(function (p) {
    var size = d.isSelected(p) ? 34 : 28;
    var icon = L.divIcon({ className: "pin-wrap", html: d.pinHtml(p), iconSize: [size, size] });
    L.marker([p.lat, p.lng], { icon: icon, zIndexOffset: d.isSelected(p) ? 1000 : 0 }).addTo(map)
      .bindPopup(d.popupHtml(p));
    bounds.push([p.lat, p.lng]);
  });
  if (d.points.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  return true;
};
