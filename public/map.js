// 트립핀 지도 (네이버 지도 API v3 · Web Dynamic Map, 실패 시 Leaflet + OpenStreetMap)
// 버전 기록
// v0.1 (2026-11-18) 장소 마커 표시, 순위 번호 마커, 마커 클릭 시 상세로 이동(유입 경로 map)
// v0.2 (2026-11-19) 출발점을 #map-data의 origin에서 읽음 (현재 위치 반영). 형식: {"origin": [위도, 경도], "points": [...]}
// v0.3 (2026-11-19) 네이버 지도로 교체. 키(NAVER_MAP_CLIENT_ID)가 없거나, 스크립트 로드 실패·인증 실패·시간 초과면
//                   Leaflet(OSM) 지도(map_leaflet.js)로 자동 전환. 상세 화면에서는 그 장소 마커를 강조
//
// 키는 서버가 환경 변수에서 읽어 base.html의 window.TRIPPIN_NAVER_MAP_KEY로 내려준다 (코드에 직접 쓰지 않음).
(function () {
  var el = document.getElementById("map");
  var dataEl = document.getElementById("map-data");
  if (!el || !dataEl) return;

  // ---------------------------------------------------------------- 공통 데이터
  var raw = JSON.parse(dataEl.textContent || "{}");
  // 예전 형식(장소 배열만)도 읽을 수 있게 둔다
  var points = Array.isArray(raw) ? raw : (raw.points || []);
  var origin = (raw && raw.origin) || [36.3256, 127.4213]; // 없으면 대전 중구청 앞

  // 상세 화면(/place/번호)이면 그 장소를 강조한다
  var m = window.location.pathname.match(/^\/place\/(\d+)/);
  var selectedId = m ? Number(m[1]) : null;

  // 마커를 눌러 상세로 갈 때 지금 검색 조건을 유지하고 유입 경로(src=map)를 붙인다
  var keep = new URLSearchParams(window.location.search);
  keep.delete("src");

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  var d = {
    origin: origin,
    points: points,
    isSelected: function (p) { return selectedId !== null && p.id === selectedId; },
    label: function (p) { return p.rank ? String(p.rank) : "•"; },
    href: function (p) {
      var params = new URLSearchParams(keep);
      params.set("src", p.src || "map");
      return "/place/" + p.id + "?" + params.toString();
    },
    pinHtml: function (p) {
      // 강조 스타일은 임시 (최종 디자인은 일요일에 style.css에서)
      var style = d.isSelected(p) ? ' style="width:34px;height:34px;background:#F06543;font-size:15px"' : "";
      return '<span class="pin"' + style + ">" + esc(d.label(p)) + "</span>";
    },
    popupHtml: function (p) { return '<a href="' + esc(d.href(p)) + '">' + esc(p.name) + "</a>"; }
  };

  // ---------------------------------------------------------------- Leaflet 폴백
  var mode = "loading"; // loading → naver | leaflet
  var timer = null;

  function useLeaflet(reason) {
    if (mode === "leaflet") return;
    mode = "leaflet";
    if (timer) clearTimeout(timer);
    if (window.console) console.info("[Trippin] OSM 지도로 전환:", reason);
    // 네이버 지도가 이미 그려졌거나 오류 화면을 띄웠을 수 있으므로 지도 칸을 새로 만든다
    var fresh = el.cloneNode(false);
    el.parentNode.replaceChild(fresh, el);
    el = fresh;
    if (window.TrippinMap && window.TrippinMap.leaflet) window.TrippinMap.leaflet(el, d);
  }

  // ---------------------------------------------------------------- 네이버 지도
  function useNaver() {
    if (mode !== "loading") return; // 이미 시간 초과로 폴백했으면 무시
    if (!(window.naver && naver.maps && naver.maps.Map)) return useLeaflet("naver.maps 없음");
    mode = "naver";
    clearTimeout(timer);
    var nm = naver.maps;

    var center = new nm.LatLng(origin[0], origin[1]);
    var map = new nm.Map(el, { center: center, zoom: 14 });
    var info = new nm.InfoWindow({ content: "", borderWidth: 1, disableAnchor: false });

    // 출발점 (현재 위치 또는 대전 중구청 앞)
    new nm.Marker({
      position: center, map: map, title: "📍",
      icon: {
        content: '<span style="display:block;width:14px;height:14px;border-radius:50%;' +
                 'background:#2F86FF;border:2px solid #1E5BD8"></span>',
        anchor: new nm.Point(9, 9)
      }
    });

    var south = origin[0], north = origin[0], west = origin[1], east = origin[1];
    points.forEach(function (p) {
      var size = d.isSelected(p) ? 34 : 28;
      var marker = new nm.Marker({
        position: new nm.LatLng(p.lat, p.lng), map: map, title: p.name,
        zIndex: d.isSelected(p) ? 1000 : 100,
        icon: { content: d.pinHtml(p), anchor: new nm.Point(size / 2, size / 2) }
      });
      nm.Event.addListener(marker, "click", function () {
        if (info.getMap() && info._trippinId === p.id) { info.close(); return; }
        info.setContent('<div style="padding:8px 12px;font-size:14px">' + d.popupHtml(p) + "</div>");
        info._trippinId = p.id;
        info.open(map, marker);
      });
      south = Math.min(south, p.lat); north = Math.max(north, p.lat);
      west = Math.min(west, p.lng); east = Math.max(east, p.lng);
    });
    nm.Event.addListener(map, "click", function () { info.close(); });

    if (points.length) {
      var bounds = new nm.LatLngBounds(new nm.LatLng(south, west), new nm.LatLng(north, east));
      map.fitBounds(bounds, { top: 30, right: 30, bottom: 30, left: 30 });
      if (map.getZoom() > 16) map.setZoom(16);
    }
  }

  var key = window.TRIPPIN_NAVER_MAP_KEY;
  if (!key) return useLeaflet("네이버 지도 키 없음");

  // 인증 실패(서비스 URL 불일치, 잘못된 키 등) 시 네이버 지도가 부르는 함수
  window.navermap_authFailure = function () { useLeaflet("네이버 지도 인증 실패"); };

  var script = document.createElement("script");
  script.src = "https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=" + encodeURIComponent(key);
  script.onload = useNaver;
  script.onerror = function () { useLeaflet("네이버 지도 스크립트 로드 실패"); };
  timer = setTimeout(function () { if (mode === "loading") useLeaflet("네이버 지도 로드 시간 초과"); }, 8000);
  document.head.appendChild(script);
})();
