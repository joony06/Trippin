// 트립핀 지도 (네이버 지도 API v3 · Web Dynamic Map, 실패 시 Leaflet + OpenStreetMap)
// 버전 기록
// v0.1 (2026-11-18) 장소 마커 표시, 순위 번호 마커, 마커 클릭 시 상세로 이동(유입 경로 map)
// v0.2 (2026-11-19) 출발점을 #map-data의 origin에서 읽음 (현재 위치 반영). 형식: {"origin": [위도, 경도], "points": [...]}
// v0.3 (2026-11-19) 네이버 지도로 교체. 키(NAVER_MAP_CLIENT_ID)가 없거나, 스크립트 로드 실패·인증 실패·시간 초과면
//                   Leaflet(OSM) 지도(map_leaflet.js)로 자동 전환. 상세 화면에서는 그 장소 마커를 강조
// v0.4 (2026-11-21) 최종 디자인: 핀을 물방울 모양(.pin, 선택은 .pin.on)으로, 기준점을 핀 끝(아래)으로
// v0.5 (2026-11-21) 지도 로딩 화면(#map-loading): 지도가 실제로 그려진 뒤에 숨김 (네이버 인증 실패 화면이 잠깐 보이던 문제)
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
    pinSize: function (p) { return p.rank ? (d.isSelected(p) ? 38 : 30) : (d.isSelected(p) ? 30 : 18); },
    // 물방울 핀은 45도 돌린 네모라서, 핀 끝은 가운데에서 아래로 한 변 × 0.707 만큼 내려간 곳
    pinAnchor: function (p) { var s = d.pinSize(p); return [s / 2, Math.round(s / 2 + s * 0.707)]; },
    pinHtml: function (p) {
      var s = d.pinSize(p);
      return '<span class="pin' + (d.isSelected(p) ? " on" : "") + (p.rank ? "" : " dot") +
             '" style="width:' + s + "px;height:" + s + 'px"><b>' + esc(p.rank ? d.label(p) : "") + "</b></span>";
    },
    popupHtml: function (p) { return '<a href="' + esc(d.href(p)) + '">' + esc(p.name) + "</a>"; }
  };

  // ---------------------------------------------------------------- Leaflet 폴백
  var mode = "loading"; // loading → naver | leaflet
  var timer = null;

  // 우리 로딩 화면: 지도가 그려진 뒤에 숨긴다. 무슨 일이 있어도 12초 뒤에는 숨긴다
  var loadingEl = document.getElementById("map-loading");
  function hideLoading() { if (loadingEl) loadingEl.classList.add("done"); }
  setTimeout(hideLoading, 12000);

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
    hideLoading();
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
        content: '<span style="display:block;width:16px;height:16px;border-radius:50%;' +
                 'background:#2F86FF;border:3px solid #fff;box-shadow:0 0 0 5px rgba(47,134,255,.25)"></span>',
        anchor: new nm.Point(9, 9)
      }
    });

    var south = origin[0], north = origin[0], west = origin[1], east = origin[1];
    points.forEach(function (p) {
      var anchor = d.pinAnchor(p);
      var marker = new nm.Marker({
        position: new nm.LatLng(p.lat, p.lng), map: map, title: p.name,
        zIndex: d.isSelected(p) ? 1000 : 100,
        icon: { content: d.pinHtml(p), anchor: new nm.Point(anchor[0], anchor[1]) }
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
    // 타일이 다 그려지고 잠시 뒤에 로딩 화면을 숨긴다. 그 사이 인증 실패가 오면 OSM으로 바뀌고 거기서 숨긴다
    nm.Event.once(map, "tilesloaded", function () {
      setTimeout(function () { if (mode === "naver") hideLoading(); }, 1200);
    });

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
