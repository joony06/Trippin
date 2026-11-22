// 트립핀 지도: 네이버 지도, 안 되면 Leaflet + OpenStreetMap
// 버전 기록
// v0.1 장소·순위 마커, 클릭 시 상세로
// v0.2 출발점 표시
// v0.3 네이버 지도로 교체, 실패 시 OSM
// v0.4 물방울 핀
// v0.5 지도 로딩 화면
// v0.6 서비스 지역 밖 어둡게, 축소 제한
// v0.7 최소 축소를 지도 칸 크기에 맞춤

(function () {
  var el = document.getElementById("map");
  var dataEl = document.getElementById("map-data");
  if (!el || !dataEl) return;

  var raw = JSON.parse(dataEl.textContent || "{}");
  var points = Array.isArray(raw) ? raw : (raw.points || []);
  var origin = (raw && raw.origin) || [36.3256, 127.4213]; // 없으면 대전 중구청 앞

  var m = window.location.pathname.match(/^\/place\/(\d+)/);
  var selectedId = m ? Number(m[1]) : null;

  // 상세 이동 시 검색 조건 유지 + src=map
  var keep = new URLSearchParams(window.location.search);
  keep.delete("src");

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  var area = null, waiting = [];
  fetch("/service_area.json").then(function (r) { return r.json(); }).then(function (a) {
    area = a; waiting.forEach(function (cb) { cb(a); }); waiting = [];
  }).catch(function () {  });

  var d = {
    // 중구 밖 어둡게 처리
    WORLD: [[33.0, 124.0], [33.0, 132.0], [39.0, 132.0], [39.0, 124.0]],
    MIN_ZOOM: 11,
    MASK: { fill: "#1B2440", fillOpacity: 0.28, stroke: "#1E5BD8", weight: 2 },
    withArea: function (cb) { if (area) cb(area); else waiting.push(cb); },
    // 대전이 지도 칸에 꽉 차는 확대 단계
    fitZoom: function (box, b) {
      var w = box.clientWidth || 800, h = box.clientHeight || 600;
      var y = function (lat) { var s = Math.sin(lat * Math.PI / 180); return Math.log((1 + s) / (1 - s)) / (4 * Math.PI); };
      var zx = Math.log2(w * 360 / (256 * (b[1][1] - b[0][1])));
      var zy = Math.log2(h / (256 * (y(b[1][0]) - y(b[0][0]))));
      return Math.max(8, Math.floor(Math.min(zx, zy)));
    },
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
    // 핀 끝 = 가운데 + 한 변 × 0.707
    pinAnchor: function (p) { var s = d.pinSize(p); return [s / 2, Math.round(s / 2 + s * 0.707)]; },
    pinHtml: function (p) {
      var s = d.pinSize(p);
      return '<span class="pin' + (d.isSelected(p) ? " on" : "") + (p.rank ? "" : " dot") +
             '" style="width:' + s + "px;height:" + s + 'px"><b>' + esc(p.rank ? d.label(p) : "") + "</b></span>";
    },
    popupHtml: function (p) { return '<a href="' + esc(d.href(p)) + '">' + esc(p.name) + "</a>"; }
  };

  var mode = "loading"; // loading → naver | leaflet
  var timer = null;

  // 지도 표시 후 로딩 화면 숨김 (최대 12초)
  var loadingEl = document.getElementById("map-loading");
  function hideLoading() { if (loadingEl) loadingEl.classList.add("done"); }
  setTimeout(hideLoading, 12000);

  function useLeaflet(reason) {
    if (mode === "leaflet") return;
    mode = "leaflet";
    if (timer) clearTimeout(timer);
    if (window.console) console.info("[Trippin] OSM 지도로 전환:", reason);
    var fresh = el.cloneNode(false);
    el.parentNode.replaceChild(fresh, el);
    el = fresh;
    if (window.TrippinMap && window.TrippinMap.leaflet) window.TrippinMap.leaflet(el, d);
    hideLoading();
  }

  function useNaver() {
    if (mode !== "loading") return;
    if (!(window.naver && naver.maps && naver.maps.Map)) return useLeaflet("naver.maps 없음");
    mode = "naver";
    clearTimeout(timer);
    var nm = naver.maps;

    var center = new nm.LatLng(origin[0], origin[1]);
    var map = new nm.Map(el, { center: center, zoom: 14, minZoom: d.MIN_ZOOM });
    d.withArea(function (a) {
      var ll = function (p) { return new nm.LatLng(p[0], p[1]); };
      new nm.Polygon({
        map: map, paths: [d.WORLD.map(ll), a.junggu.map(ll)], clickable: false, zIndex: 1,
        fillColor: d.MASK.fill, fillOpacity: d.MASK.fillOpacity,
        strokeColor: d.MASK.stroke, strokeWeight: d.MASK.weight, strokeOpacity: 0.9
      });
      var b = a.daejeon_bounds;
      map.setOptions("maxBounds", new nm.LatLngBounds(ll([b[0][0] - 0.02, b[0][1] - 0.03]), ll([b[1][0] + 0.02, b[1][1] + 0.03])));
      var minZ = d.fitZoom(el, b);
      map.setOptions("minZoom", minZ);
      if (map.getZoom() < minZ) map.setZoom(minZ);
    });
    var info = new nm.InfoWindow({ content: "", borderWidth: 1, disableAnchor: false });

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

  // 네이버 지도 인증 실패 시 호출
  window.navermap_authFailure = function () { useLeaflet("네이버 지도 인증 실패"); };

  var script = document.createElement("script");
  script.src = "https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId=" + encodeURIComponent(key);
  script.onload = useNaver;
  script.onerror = function () { useLeaflet("네이버 지도 스크립트 로드 실패"); };
  timer = setTimeout(function () { if (mode === "loading") useLeaflet("네이버 지도 로드 시간 초과"); }, 8000);
  document.head.appendChild(script);
})();
