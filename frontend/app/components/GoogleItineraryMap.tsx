"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { LngLatBoundsLike, Map as MapLibreMap, Marker as MapLibreMarker, Popup as MapLibrePopup } from "maplibre-gl";
import type { DayRouteSummary } from "../lib/routeTypes";
import {
  formatPriceWithRmb,
  getCategoryLabel,
  getLocalizedDescription,
  getLocalizedPlaceName,
} from "../lib/locale";

interface Activity {
  poi_source?: { rating_known?: boolean; coordinate_system?: string } | null;
  id: number;
  name: string;
  name_zh?: string | null;
  category: string;
  cost: number;
  duration: number;
  rating: number;
  coordinates: {
    latitude: number;
    longitude: number;
  };
  tags?: string[] | null;
  description?: string | null;
  description_zh?: string | null;
}

interface GoogleItineraryMapProps {
  activities: Activity[];
  currencyCode?: string;
  routeSummary?: DayRouteSummary | null;
}

declare global {
  interface Window {
    AMap?: any;
    __amapLoaderPromise__?: Promise<any>;
  }
}

type MapProvider = "amap" | "osm";
type MapState = "loading" | "ready" | "error";

const AMAP_KEY = process.env.NEXT_PUBLIC_AMAP_KEY || "";
const AMAP_SCRIPT_ID = "amap-jsapi-script";

const getCategoryColor = (category: string): string => {
  const colors: { [key: string]: string } = {
    food: "#10b981",
    culture: "#8b5cf6",
    nightlife: "#ec4899",
    nature: "#22c55e",
    shopping: "#f59e0b",
    adventure: "#ef4444",
    beaches: "#06b6d4",
  };
  return colors[category.toLowerCase()] || "#6366f1";
};

function escapeHtml(text: string): string {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function buildInfoWindowContent(activity: Activity, index: number, currencyCode: string): string {
  const localizedName = getLocalizedPlaceName(activity.name, activity.name_zh);
  const localizedDescription = getLocalizedDescription(activity.description, activity.description_zh);
  return `
    <div style="padding: 8px; max-width: 240px;">
      <div style="font-weight: 700; color: #111827; margin-bottom: 6px; font-size: 14px;">
        ${index + 1}. ${escapeHtml(localizedName)}
      </div>
      ${localizedDescription ? `<div style="font-size: 12px; color: #4b5563; margin-bottom: 8px;">${escapeHtml(localizedDescription)}</div>` : ""}
      <div style="display: flex; flex-wrap: wrap; gap: 6px; font-size: 12px;">
        <span style="padding: 4px 8px; background: #f3e8ff; color: #6d28d9; border-radius: 999px;">${escapeHtml(getCategoryLabel(activity.category))}</span>
        <span style="padding: 4px 8px; background: #fef3c7; color: #a16207; border-radius: 999px;">${activity.poi_source?.rating_known === false ? "评分未知" : `⭐ ${activity.rating.toFixed(1)}`}</span>
        <span style="padding: 4px 8px; background: #dcfce7; color: #15803d; border-radius: 999px;">${escapeHtml(formatPriceWithRmb(activity.cost, currencyCode))}</span>
        <span style="padding: 4px 8px; background: #dbeafe; color: #1d4ed8; border-radius: 999px;">${activity.duration} 分钟</span>
      </div>
    </div>
  `;
}

function buildMarkerBubble(index: number, category: string): HTMLDivElement {
  const el = document.createElement("div");
  el.style.width = "24px";
  el.style.height = "24px";
  el.style.borderRadius = "999px";
  el.style.background = getCategoryColor(category);
  el.style.border = "2px solid #ffffff";
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.color = "#ffffff";
  el.style.fontSize = "12px";
  el.style.fontWeight = "700";
  el.style.boxShadow = "0 4px 14px rgba(15, 23, 42, 0.35)";
  el.textContent = String(index + 1);
  return el;
}

function isChinaCoordinate(latitude: number, longitude: number): boolean {
  return latitude >= 18 && latitude <= 54 && longitude >= 73 && longitude <= 135;
}

function loadAmapScript(): Promise<any> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("AMap can only be loaded in the browser."));
  }

  if (window.AMap) {
    return Promise.resolve(window.AMap);
  }

  if (window.__amapLoaderPromise__) {
    return window.__amapLoaderPromise__;
  }

  if (!AMAP_KEY) {
    return Promise.reject(new Error("NEXT_PUBLIC_AMAP_KEY is not configured."));
  }

  window.__amapLoaderPromise__ = new Promise((resolve, reject) => {
    const existing = document.getElementById(AMAP_SCRIPT_ID) as HTMLScriptElement | null;

    if (existing) {
      existing.addEventListener("load", () => resolve(window.AMap));
      existing.addEventListener("error", () => reject(new Error("Failed to load AMap script.")));
      return;
    }

    const script = document.createElement("script");
    script.id = AMAP_SCRIPT_ID;
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_KEY}&plugin=AMap.Scale,AMap.ToolBar`;
    script.async = true;
    script.onload = () => resolve(window.AMap);
    script.onerror = () => reject(new Error("Failed to load AMap script."));
    document.head.appendChild(script);
  });

  return window.__amapLoaderPromise__;
}

export default function GoogleItineraryMap({ activities, currencyCode = "USD", routeSummary }: GoogleItineraryMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const providerRef = useRef<MapProvider | null>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]);
  const popupRef = useRef<MapLibrePopup | null>(null);
  const [mapState, setMapState] = useState<MapState>("loading");

  const validActivities = useMemo(
    () =>
      activities.filter(
        (act) => act.coordinates.latitude !== 0 || act.coordinates.longitude !== 0
      ),
    [activities]
  );

  const provider: MapProvider = useMemo(() => {
    const allInChina = validActivities.every((activity) =>
      isChinaCoordinate(activity.coordinates.latitude, activity.coordinates.longitude)
    );
    return allInChina && AMAP_KEY ? "amap" : "osm";
  }, [validActivities]);

  useEffect(() => {
    providerRef.current = provider;
    setMapState("loading");
  }, [provider]);

  useEffect(() => {
    if (!containerRef.current || validActivities.length === 0) {
      return;
    }

    let cancelled = false;

    const destroyExistingMap = () => {
      overlaysRef.current.forEach((overlay) => {
        try {
          if (providerRef.current === "amap" && mapRef.current) {
            mapRef.current.remove(overlay);
          } else if (typeof overlay.remove === "function") {
            overlay.remove();
          }
        } catch {}
      });
      overlaysRef.current = [];
      popupRef.current?.remove();
      popupRef.current = null;
      if (mapRef.current) {
        try {
          mapRef.current.remove?.();
          mapRef.current.destroy?.();
        } catch {}
        mapRef.current = null;
      }
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };

    destroyExistingMap();

    const initAmap = async () => {
      const AMap = await loadAmapScript();
      if (cancelled || !containerRef.current) {
        return;
      }

      const center: [number, number] = [
        validActivities[0].coordinates.longitude,
        validActivities[0].coordinates.latitude,
      ];

      const map = new AMap.Map(containerRef.current, {
        viewMode: "2D",
        resizeEnable: true,
        zoom: 13,
        center,
        mapStyle: "amap://styles/normal",
      });

      if (AMap.Scale) {
        map.addControl(new AMap.Scale());
      }
      if (AMap.ToolBar) {
        map.addControl(new AMap.ToolBar({ position: "RT" }));
      }

      const infoWindow = new AMap.InfoWindow({ offset: new AMap.Pixel(0, -24) });
      const markers = validActivities.map((activity, index) => {
        const marker = new AMap.Marker({
          position: [activity.coordinates.longitude, activity.coordinates.latitude],
          anchor: "center",
          content: buildMarkerBubble(index, activity.category),
        });

        marker.on("click", () => {
          infoWindow.setContent(buildInfoWindowContent(activity, index, currencyCode));
          infoWindow.open(map, marker.getPosition());
        });
        return marker;
      });

      const lines = routeSummary ? routeSummary.legs.flatMap(leg => {
        const paths = leg.geometry.length ? leg.geometry : [[[leg.origin.longitude, leg.origin.latitude], [leg.destination.longitude, leg.destination.latitude]]];
        return paths.map(path => new AMap.Polyline({ path, strokeColor: leg.source === "amap" ? "#06b6d4" : "#f59e0b",
          strokeWeight: 5, strokeOpacity: .85, strokeStyle: leg.geometry.length ? "solid" : "dashed", showDir: true }));
      }) : [new AMap.Polyline({
        path: validActivities.map(activity => [activity.coordinates.longitude, activity.coordinates.latitude]),
        strokeColor: "#6366f1", strokeOpacity: .85, strokeWeight: 5, strokeStyle: "dashed", showDir: true,
      })];
      const hotelMarkers = [];
      if (routeSummary) {
        const bubble = buildMarkerBubble(0, "food");
        bubble.textContent = "住";
        const hotel = new AMap.Marker({ position: [routeSummary.lodging.longitude, routeSummary.lodging.latitude], content: bubble, anchor: "center" });
        hotel.on("click", () => { infoWindow.setContent(escapeHtml(routeSummary.lodging.name)); infoWindow.open(map, hotel.getPosition()); });
        hotelMarkers.push(hotel);
      }
      overlaysRef.current = [...markers, ...hotelMarkers, ...lines];
      map.add(overlaysRef.current);
      map.setFitView(overlaysRef.current, false, [60, 60, 60, 60]);
      mapRef.current = map;
      providerRef.current = "amap";
      setMapState("ready");
    };

    const initOsmMap = async () => {
      // AMap supplies GCJ-02. Do not silently place those coordinates on a
      // WGS-84 basemap when the browser map key is missing.
      if (validActivities.some(activity => activity.poi_source?.coordinate_system === "GCJ02")) {
        throw new Error("高德地点需要高德地图 Key；不能直接显示在不同坐标系的底图上。");
      }
      const maplibre = await import("maplibre-gl");
      if (cancelled || !containerRef.current) {
        return;
      }

      const bounds = validActivities.reduce(
        (acc, activity) => {
          acc.minLng = Math.min(acc.minLng, activity.coordinates.longitude);
          acc.maxLng = Math.max(acc.maxLng, activity.coordinates.longitude);
          acc.minLat = Math.min(acc.minLat, activity.coordinates.latitude);
          acc.maxLat = Math.max(acc.maxLat, activity.coordinates.latitude);
          return acc;
        },
        {
          minLng: validActivities[0].coordinates.longitude,
          maxLng: validActivities[0].coordinates.longitude,
          minLat: validActivities[0].coordinates.latitude,
          maxLat: validActivities[0].coordinates.latitude,
        }
      );

      const map = new maplibre.Map({
        container: containerRef.current,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
              tileSize: 256,
              attribution:
                '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
            },
          },
          layers: [
            {
              id: "osm",
              type: "raster",
              source: "osm",
            },
          ],
        },
        center: [
          validActivities[0].coordinates.longitude,
          validActivities[0].coordinates.latitude,
        ],
        zoom: 12,
      });

      map.addControl(new maplibre.NavigationControl({ visualizePitch: false }), "top-right");

      map.on("load", () => {
        if (cancelled) {
          return;
        }

        const pathGeoJson = {
          type: "Feature",
          geometry: {
            type: "LineString",
            coordinates: validActivities.map((activity) => [
              activity.coordinates.longitude,
              activity.coordinates.latitude,
            ]),
          },
          properties: {},
        } as const;

        map.addSource("route", {
          type: "geojson",
          data: pathGeoJson,
        });

        map.addLayer({
          id: "route-line",
          type: "line",
          source: "route",
          paint: {
            "line-color": "#6366f1",
            "line-width": 4,
            "line-opacity": 0.85,
          },
        });

        popupRef.current = new maplibre.Popup({
          closeButton: true,
          closeOnClick: false,
          offset: 18,
        });

        const markers = validActivities.map((activity, index) => {
          const marker = new maplibre.Marker({
            element: buildMarkerBubble(index, activity.category),
            anchor: "center",
          })
            .setLngLat([
              activity.coordinates.longitude,
              activity.coordinates.latitude,
            ])
            .setPopup(
              new maplibre.Popup({
                closeButton: true,
                closeOnClick: false,
                offset: 18,
              }).setHTML(buildInfoWindowContent(activity, index, currencyCode))
            )
            .addTo(map);

          return marker;
        });

        overlaysRef.current = markers;
        map.fitBounds(
          [
            [bounds.minLng, bounds.minLat],
            [bounds.maxLng, bounds.maxLat],
          ] as LngLatBoundsLike,
          { padding: 60, maxZoom: 14 }
        );

        mapRef.current = map;
        providerRef.current = "osm";
        setMapState("ready");
      });
    };

    const initMap = async () => {
      try {
        if (provider === "amap") {
          await initAmap();
        } else {
          await initOsmMap();
        }
      } catch (error) {
        console.error("Map initialization failed:", error);
        if (!cancelled) {
          setMapState("error");
        }
      }
    };

    initMap();

    return () => {
      cancelled = true;
      destroyExistingMap();
    };
  }, [currencyCode, provider, validActivities, routeSummary]);

  if (validActivities.length === 0) {
    return (
      <div className="w-full h-96 bg-gray-50 rounded-lg flex items-center justify-center border-2 border-gray-200">
        <p className="text-gray-500 font-medium">暂无可展示的地点</p>
      </div>
    );
  }

  if (mapState === "error") {
    return (
      <div className="w-full min-h-[400px] rounded-2xl border border-red-400/30 bg-red-500/10 p-6 text-white">
        <h3 className="text-lg font-bold mb-2">地图加载失败</h3>
        <p className="text-sm text-gray-200">
          {provider === "osm" && validActivities.some(a => a.poi_source?.coordinate_system === "GCJ02")
            ? "这些地点使用高德坐标，需要配置前端高德地图 Key 后展示。"
            : "当前地图提供方："}
          {provider === "amap" ? "高德地图" : "OpenStreetMap / MapLibre"}。
          请检查网络连接，或稍后重试。
        </p>
      </div>
    );
  }

  return (
    <div className="relative">
      <div
        ref={containerRef}
        style={{ width: "100%", height: "400px", borderRadius: "1rem", overflow: "hidden" }}
      />

      {mapState === "loading" && (
        <div className="absolute inset-0 flex items-center justify-center rounded-2xl bg-gray-100/95">
          <p className="text-gray-500">
            {provider === "amap" ? "高德地图加载中..." : "OpenStreetMap 加载中..."}
          </p>
        </div>
      )}

      <div className="absolute top-4 left-4 rounded-full bg-white/95 px-3 py-1 text-xs font-semibold text-gray-700 shadow">
        {provider === "amap" ? "中国城市 · 高德地图" : "海外城市 · OpenStreetMap"}
      </div>

      <div className="absolute bottom-4 left-4 bg-white rounded-lg shadow-lg p-3 text-xs">
        <p className="font-semibold text-gray-700 mb-2">{routeSummary ? "实线：道路方案 · 虚线：示意" : "游览顺序示意（非道路导航）"}</p>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-primary-500 border-2 border-white flex items-center justify-center">
            <span className="text-white text-[8px] font-bold">1</span>
          </div>
          <span className="text-gray-600">→</span>
          <div className="w-4 h-4 rounded-full bg-primary-500 border-2 border-white flex items-center justify-center">
            <span className="text-white text-[8px] font-bold">2</span>
          </div>
          <span className="text-gray-600">→</span>
          <div className="w-4 h-4 rounded-full bg-primary-500 border-2 border-white flex items-center justify-center">
            <span className="text-white text-[8px] font-bold">n</span>
          </div>
        </div>
        <p className="text-gray-500 mt-1 text-[10px]">点击标记查看详情</p>
      </div>
    </div>
  );
}
