"use client";

import { useState } from "react";
import { useSession, signIn } from "next-auth/react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import Toast from "./Toast";
import ActivityModal from "./ActivityModal";
import { api } from "../lib/api";
import {
  formatChineseDate,
  formatChineseShortDate,
  formatChineseTime,
  formatChineseWeekday,
  formatPriceWithRmb,
  getCategoryLabel,
} from "../lib/locale";

// Dynamic import for Google Maps to avoid SSR issues
const GoogleItineraryMap = dynamic(() => import("./GoogleItineraryMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-96 bg-gray-100 rounded-lg flex items-center justify-center">
      <p className="text-gray-500">地图加载中...</p>
    </div>
  ),
});

interface City {
  id: number;
  name: string;
  country: string;
}

interface ActivitySummary {
  id: number;
  name: string;
  category: string;
  cost: number;
  duration: number;
  rating: number;
  coordinates: {
    latitude: number;
    longitude: number;
  };
}

interface ItineraryBlock {
  start_time: string;
  end_time: string;
  activity: ActivitySummary;
  travel_time_from_previous?: number;
}

interface ItineraryDay {
  date: string;
  total_cost: number;
  blocks: ItineraryBlock[];
}

interface CityItinerary {
  city_id: number;
  city_name: string;
  country: string;
  days_allocated: number;
  start_date: string;
  end_date: string;
  budget_allocated?: number;
  estimated_cost: number;
  narrative?: {
    narrative_text: string;
    tips?: string;
  } | null;
  itinerary: {
    days: ItineraryDay[];
    summary: {
      total_cost: number;
      categories_covered: string[];
    };
  };
}

interface MultiCityPlan {
  total_cities: number;
  total_days: number;
  total_budget?: number;
  total_estimated_cost: number;
  budget_remaining?: number;
  cities: CityItinerary[];
  trip_start: string;
  trip_end: string;
  pace: string;
  interests: string[];
}

interface MultiCityResultsProps {
  tripPlan: MultiCityPlan;
  onStartOver: () => void;
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function MultiCityResults({
  tripPlan,
  onStartOver,
}: MultiCityResultsProps) {
  const { data: session } = useSession();
  const router = useRouter();
  const [expandedCity, setExpandedCity] = useState<number | null>(
    tripPlan.cities[0]?.city_id || null
  );
  // Per-city active day index
  const [activeDayByCity, setActiveDayByCity] = useState<Record<number, number>>(
    Object.fromEntries(tripPlan.cities.map(c => [c.city_id, 0]))
  );
  // Per-city mutable itinerary (for refine updates)
  const [cityItineraries, setCityItineraries] = useState<Record<number, CityItinerary>>(
    Object.fromEntries(tripPlan.cities.map(c => [c.city_id, c]))
  );
  // Per-city refine state
  const [refineMessage, setRefineMessage] = useState<Record<number, string>>({});
  const [isRefining, setIsRefining] = useState<Record<number, boolean>>({});
  const [refineResult, setRefineResult] = useState<Record<number, string | null>>({});
  const [selectedActivity, setSelectedActivity] = useState<ActivitySummary | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type: "error" | "success" | "info" } | null>(null);

  const handleRefineCity = async (cityPlan: CityItinerary) => {
    const cityId = cityPlan.city_id;
    const msg = refineMessage[cityId]?.trim();
    if (!msg) return;

    setIsRefining(prev => ({ ...prev, [cityId]: true }));
    setRefineResult(prev => ({ ...prev, [cityId]: null }));

    // Build preferences from city plan
    const preferences = {
      destination_city_id: cityId,
      start_date: cityPlan.start_date,
      end_date: cityPlan.end_date,
      trip_type: cityPlan.days_allocated <= 1 ? "day_trip"
        : cityPlan.days_allocated <= 3 ? "weekend"
        : cityPlan.days_allocated <= 7 ? "one_week" : "long",
      budget_level: "medium" as const,
      energy_level: tripPlan.pace === "relaxed" ? "relaxed"
        : tripPlan.pace === "packed" ? "active" : "moderate",
      travel_mode: "mixed" as const,
      preferred_categories: tripPlan.interests || [],
    };

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/refine-itinerary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          itinerary: {
            days: cityPlan.itinerary.days,
            summary: {
              total_cost: cityPlan.itinerary.summary.total_cost,
              avg_cost_per_day: cityPlan.days_allocated > 0
                ? cityPlan.itinerary.summary.total_cost / cityPlan.days_allocated
                : cityPlan.itinerary.summary.total_cost,
              categories_covered: cityPlan.itinerary.summary.categories_covered,
              pace_label: tripPlan.pace,
            },
            optimization_score: 0.85,
            confidence_score: 0.90,
            narrative: {
              narrative_text: cityPlan.narrative?.narrative_text ?? "",
            },
          },
          preferences,
          user_message: msg,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        // Merge updated itinerary days back into this city
        setCityItineraries(prev => ({
          ...prev,
          [cityId]: {
            ...prev[cityId],
            itinerary: {
              ...prev[cityId].itinerary,
              days: data.itinerary.days,
              summary: data.itinerary.summary ?? prev[cityId].itinerary.summary,
            },
          },
        }));
        setActiveDayByCity(prev => ({ ...prev, [cityId]: 0 }));
        setRefineResult(prev => ({ ...prev, [cityId]: data.assistant_message }));
        setRefineMessage(prev => ({ ...prev, [cityId]: "" }));
      } else {
        const err = await response.json();
        const detail = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
        setRefineResult(prev => ({ ...prev, [cityId]: `暂时无法应用修改：${detail || "未知错误"}` }));
      }
    } catch {
      setRefineResult(prev => ({ ...prev, [cityId]: "请求失败，请确认后端是否已启动。" }));
    } finally {
      setIsRefining(prev => ({ ...prev, [cityId]: false }));
    }
  };

  const toggleCity = (cityId: number) => {
    setExpandedCity(expandedCity === cityId ? null : cityId);
  };

  const formatDate = (dateStr: string) => formatChineseDate(dateStr, true);
  const formatTime = (timeStr: string) => formatChineseTime(timeStr);


  const handleShareItinerary = async () => {
    // Must be signed in to share
    if (!session) {
      setToast({
        message: "请先登录，再保存或分享你的行程。",
        type: "info"
      });
      setTimeout(() => signIn("google"), 1500);
      return;
    }

    setIsSharing(true);
    try {
      const authToken = (session as any)?.accessToken;

      // Convert multi-city plan to saved itinerary format
      const allDays = tripPlan.cities.flatMap(city => city.itinerary.days);

      // Build city_segments from the trip plan
      const citySegments = tripPlan.cities.map((city, index) => ({
        city_id: city.city_id,
        stay_duration_days: city.days_allocated,
        travel_time_from_previous_hours: index > 0 ? 2 : null,
      }));

      const tripPreferences = {
        start_date: tripPlan.trip_start,
        end_date: tripPlan.trip_end,
        city_segments: citySegments,
        trip_type: tripPlan.total_days <= 1 ? "day_trip" :
                   tripPlan.total_days <= 3 ? "weekend" :
                   tripPlan.total_days <= 7 ? "one_week" : "long",
        budget_level: "medium" as const,
        preferred_categories: tripPlan.interests || [],
        energy_level: tripPlan.pace === "relaxed" ? "relaxed" :
                      tripPlan.pace === "packed" ? "active" : "moderate",
        travel_mode: "mixed" as const,
      };

      const itinerary = {
        days: allDays,
        summary: {
          total_cost: tripPlan.total_estimated_cost,
          avg_cost_per_day: tripPlan.total_estimated_cost / tripPlan.total_days,
          categories_covered: [...new Set(tripPlan.cities.flatMap(c => c.itinerary.summary.categories_covered))],
          pace_label: tripPlan.pace,
        },
        optimization_score: 0.85,
        confidence_score: 0.90,
        narrative: {
          narrative_text: `这是一趟覆盖 ${tripPlan.total_cities} 座城市、共 ${tripPlan.total_days} 天的多城市旅行。你将依次前往 ${tripPlan.cities.map(c => c.city_name).join("、")}，整体节奏为 ${tripPlan.pace}。`,
          explanations: `系统会按照城市顺序帮你安排每日活动，并尽量让路线更顺畅。`,
          tips: "建议提前确认酒店、城市间交通和证件要求。"
        }
      };

      const savedItinerary = await api.saveItinerary({
        trip_preferences: tripPreferences,
        itinerary: itinerary,
        is_public: true // Make it public for sharing
      }, authToken);

      if (savedItinerary.share_url) {
        setShareUrl(savedItinerary.share_url);
        await navigator.clipboard.writeText(savedItinerary.share_url);
        setToast({ message: "分享链接已复制到剪贴板！", type: "success" });
      }
    } catch (error) {
      console.error("Share itinerary error:", error);
      setToast({ message: "创建分享链接失败", type: "error" });
    } finally {
      setIsSharing(false);
    }
  };

  const handleSaveItinerary = async () => {
    // If not signed in, show prompt to sign in
    if (!session) {
      setToast({
        message: "请先登录，保存后可在任何设备查看你的行程。",
        type: "info"
      });
      setTimeout(() => signIn("google"), 1500);
      return;
    }

    setIsSaving(true);
    try {
      // Get auth token from session
      const authToken = (session as any)?.accessToken;

      // Convert multi-city plan to saved itinerary format
      const allDays = tripPlan.cities.flatMap(city => city.itinerary.days);
      const cityNames = tripPlan.cities.map(c => c.city_name).join(", ");

      // Build city_segments from the trip plan
      const citySegments = tripPlan.cities.map((city, index) => ({
        city_id: city.city_id,
        stay_duration_days: city.days_allocated,
        travel_time_from_previous_hours: index > 0 ? 2 : null, // Estimate 2 hours travel between cities
      }));

      // Build trip_preferences object matching backend schema
      const tripPreferences = {
        start_date: tripPlan.trip_start,
        end_date: tripPlan.trip_end,
        city_segments: citySegments, // For multi-city trips, use city_segments
        trip_type: tripPlan.total_days <= 1 ? "day_trip" :
                   tripPlan.total_days <= 3 ? "weekend" :
                   tripPlan.total_days <= 7 ? "one_week" : "long",
        budget_level: "medium" as const, // Default to medium since we don't track budget level
        preferred_categories: tripPlan.interests || [],
        energy_level: tripPlan.pace === "relaxed" ? "relaxed" :
                      tripPlan.pace === "packed" ? "active" : "moderate",
        travel_mode: "mixed" as const, // Multi-city trips use mixed travel
      };

      // Build itinerary object matching backend schema
      const itinerary = {
        days: allDays,
        summary: {
          total_cost: tripPlan.total_estimated_cost,
          avg_cost_per_day: tripPlan.total_estimated_cost / tripPlan.total_days,
          categories_covered: [...new Set(tripPlan.cities.flatMap(c => c.itinerary.summary.categories_covered))],
          pace_label: tripPlan.pace,
        },
        optimization_score: 0.85, // Default score
        confidence_score: 0.90, // Default score
        narrative: {
          narrative_text: `这是一趟覆盖 ${tripPlan.total_cities} 座城市、共 ${tripPlan.total_days} 天的多城市旅行。你将依次前往 ${cityNames}，整体节奏为 ${tripPlan.pace}。`,
          explanations: "系统会按照城市顺序帮你安排每日活动，并尽量让路线更顺畅。",
          tips: "建议提前确认酒店、城市间交通和证件要求。"
        }
      };

      await api.saveItinerary({
        trip_preferences: tripPreferences,
        itinerary: itinerary,
        is_public: false
      }, authToken);

      setToast({ message: "行程已成功保存！", type: "success" });

      // Redirect to My Itineraries after successful save
      setTimeout(() => router.push("/my-itineraries"), 1500);
    } catch (error) {
      setToast({ message: "保存行程失败", type: "error" });
    } finally {
      setIsSaving(false);
    }
  };

  const categoryColors: Record<string, string> = {
    food: "bg-emerald-500", culture: "bg-purple-500", nightlife: "bg-pink-500",
    nature: "bg-green-500", shopping: "bg-amber-500", adventure: "bg-red-500", beaches: "bg-cyan-500",
  };
  const categoryIcons: Record<string, string> = {
    food: "🍽️", culture: "🏛️", nightlife: "🌙", nature: "🌿",
    shopping: "🛍️", adventure: "⛰️", beaches: "🏖️",
  };

  return (
    <div className="space-y-6">
      {/* Trip Summary Header */}
      <div className="glass-card rounded-2xl p-6 border border-purple-500/20">
        <div className="flex items-start justify-between mb-6 flex-wrap gap-4">
          <div>
            <h2 className="text-3xl font-bold gradient-text mb-1">
              {tripPlan.total_cities} 城市旅行方案
            </h2>
            <p className="text-gray-400">
              {formatDate(tripPlan.trip_start)} — {formatDate(tripPlan.trip_end)}
            </p>
            <div className="flex gap-2 mt-2 flex-wrap">
              {tripPlan.cities.map((c, i) => (
                <span key={c.city_id} className="text-gray-300 text-sm">
                  {c.city_name}{i < tripPlan.cities.length - 1 ? " →" : ""}
                </span>
              ))}
            </div>
          </div>
          <div className="flex gap-3 flex-wrap">
            <button
              onClick={handleShareItinerary}
              disabled={isSharing}
              className="px-4 py-2 glass-card rounded-lg text-white font-semibold hover:bg-white/10 transition-colors disabled:opacity-50"
            >
              {isSharing ? "分享中..." : "🔗 分享"}
            </button>
            <button
              onClick={handleSaveItinerary}
              disabled={isSaving}
              className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {isSaving ? "保存中..." : "💾 保存"}
            </button>
            <button
              onClick={onStartOver}
              className="px-4 py-2 glass-card rounded-lg text-white font-semibold hover:bg-white/10 transition-colors"
            >
              ← 新建行程
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="glass-card rounded-xl p-4 text-center">
            <div className="text-2xl font-bold gradient-text">{tripPlan.total_days}</div>
            <div className="text-xs text-gray-400 mt-1">总天数</div>
          </div>
          <div className="glass-card rounded-xl p-4 text-center">
            <div className="text-2xl font-bold gradient-text">{tripPlan.total_cities}</div>
            <div className="text-xs text-gray-400 mt-1">城市数</div>
          </div>
          <div className="glass-card rounded-xl p-4 text-center">
            <div className="text-2xl font-bold gradient-text">{formatPriceWithRmb(tripPlan.total_estimated_cost)}</div>
            <div className="text-xs text-gray-400 mt-1">预计花费</div>
          </div>
          <div className="glass-card rounded-xl p-4 text-center">
            <div className="text-2xl font-bold gradient-text capitalize">{tripPlan.pace}</div>
            <div className="text-xs text-gray-400 mt-1">节奏</div>
          </div>
        </div>
      </div>

      {/* City-by-City Itineraries */}
      <div className="space-y-4">
        {tripPlan.cities.map((originalCityPlan, cityIndex) => {
          const cityPlan = cityItineraries[originalCityPlan.city_id] ?? originalCityPlan;
          const activeDayIndex = activeDayByCity[cityPlan.city_id] ?? 0;
          const activeDay = cityPlan.itinerary.days[activeDayIndex];
          const isExpanded = expandedCity === cityPlan.city_id;

          return (
            <div key={cityPlan.city_id} className="glass-card rounded-2xl overflow-hidden">
              {/* City Header */}
              <button
                onClick={() => toggleCity(cityPlan.city_id)}
                className="w-full p-6 flex items-center justify-between hover:bg-white/5 transition-all"
              >
                <div className="flex items-center gap-4">
                  <div className="flex-shrink-0 w-12 h-12 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 text-white flex items-center justify-center text-xl font-bold">
                    {cityIndex + 1}
                  </div>
                  <div className="text-left">
                    <h3 className="text-2xl font-bold text-white">{cityPlan.city_name}</h3>
                    <p className="text-sm text-gray-400">
                      {cityPlan.country} · {cityPlan.days_allocated} 天 · {formatDate(cityPlan.start_date)} — {formatDate(cityPlan.end_date)}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-xs text-gray-500 mb-0.5">预计花费</div>
                    <div className="text-lg font-bold text-purple-300">{formatPriceWithRmb(cityPlan.estimated_cost)}</div>
                  </div>
                  <svg
                    className={`w-5 h-5 text-gray-400 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {/* Expanded — Two-Panel Layout (same as single-city) */}
              {isExpanded && (
                <div className="border-t border-white/10 flex bg-gray-800/60" style={{ minHeight: "600px" }}>
                  {/* Left Sidebar — Day List */}
                  <div className="w-52 shrink-0 border-r border-white/10 flex flex-col overflow-y-auto">
                    <div className="px-4 py-3 border-b border-white/10">
                      <p className="text-xs font-semibold uppercase tracking-wider text-gray-500">在 {cityPlan.city_name}</p>
                      <p className="text-sm font-bold text-white mt-0.5">共 {cityPlan.days_allocated} 天</p>
                    </div>
                    <div className="flex-1">
                      {cityPlan.itinerary.days.map((day, dayIndex) => {
                        const isActive = activeDayIndex === dayIndex;
                        const dayLabel = formatChineseWeekday(day.date);
                        const dateLabel = formatChineseShortDate(day.date);
                        const topCategories = [...new Set(day.blocks.map(b => b.activity.category))].slice(0, 3);
                        return (
                          <button
                            key={dayIndex}
                            onClick={() => setActiveDayByCity(prev => ({ ...prev, [cityPlan.city_id]: dayIndex }))}
                            className={`relative w-full text-left px-4 py-4 transition-all duration-200 border-b border-white/5 ${
                              isActive ? "bg-purple-600/20 text-white" : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
                            }`}
                          >
                            {isActive && (
                              <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gradient-to-b from-purple-500 to-pink-500" />
                            )}
                            <div className="flex items-center justify-between mb-1">
                              <span className={`text-xs font-bold uppercase tracking-wider ${isActive ? "text-purple-400" : "text-gray-600"}`}>
                                第 {dayIndex + 1} 天
                              </span>
                              <span className={`text-xs ${isActive ? "text-purple-300" : "text-gray-600"}`}>
                                {formatPriceWithRmb(day.total_cost)}
                              </span>
                            </div>
                            <div className="text-sm font-semibold mb-1">{dayLabel}，{dateLabel}</div>
                            <div className="flex gap-0.5 text-sm">
                              {topCategories.map(cat => (
                                <span key={cat} title={cat}>{categoryIcons[cat] ?? "📍"}</span>
                              ))}
                              <span className="text-xs text-gray-600 ml-1 self-center">{day.blocks.length} 个地点</span>
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {/* Right Panel — Active Day */}
                  {activeDay && (
                    <div className="flex-1 overflow-y-auto">
                      {/* Day header */}
                      <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between">
                        <div>
                          <h3 className="text-lg font-bold text-white">
                            第 {activeDayIndex + 1} 天 · {formatChineseDate(activeDay.date)}
                          </h3>
                          <p className="text-sm text-gray-400 mt-0.5">
                            {activeDay.blocks.length} 个活动
                          </p>
                        </div>
                        <span className="text-purple-300 font-semibold text-sm">
                          {formatPriceWithRmb(activeDay.total_cost)}
                        </span>
                      </div>

                      <div className="p-6">
                        {/* AI Narrative — shown once per city (on first day view) */}
                        {activeDayIndex === 0 && cityPlan.narrative?.narrative_text && (
                          <div className="glass-card rounded-2xl p-5 mb-6 border border-purple-500/20">
                            <h3 className="text-base font-bold text-white mb-2">✨ AI 行程解读 · {cityPlan.city_name}</h3>
                            <p className="text-gray-300 leading-relaxed whitespace-pre-line text-sm">
                              {cityPlan.narrative.narrative_text}
                            </p>
                          </div>
                        )}

                        {/* Map */}
                        <div className="mb-6 rounded-xl overflow-hidden mx-auto" style={{ maxWidth: "75%" }}>
                          <GoogleItineraryMap
                            key={`${cityPlan.city_id}-${activeDayIndex}`}
                            activities={activeDay.blocks.map(b => b.activity)}
                          />
                        </div>

                        {/* Timeline */}
                        <div className="space-y-1">
                          {activeDay.blocks.map((block, blockIndex) => {
                            const dotColor = categoryColors[block.activity.category] ?? "bg-indigo-500";
                            return (
                              <div key={blockIndex}>
                                {block.travel_time_from_previous && block.travel_time_from_previous > 0 && (
                                  <div className="flex items-center gap-3 pl-[52px] py-1">
                                    <div className="w-px h-5 bg-purple-500/30" />
                                    <span className="text-xs text-gray-500 flex items-center gap-1.5">
                                      🗺️ {block.travel_time_from_previous} 分钟路程
                                    </span>
                                  </div>
                                )}
                                <div
                                  className="flex items-start gap-4 p-4 rounded-xl hover:bg-white/5 transition-colors cursor-pointer group"
                                  onClick={() => setSelectedActivity(block.activity)}
                                >
                                  <div className="flex flex-col items-center gap-1 shrink-0 w-12">
                                    <div className={`w-3 h-3 rounded-full ${dotColor} ring-2 ring-gray-900 mt-1`} />
                                    <span className="text-purple-400 font-mono text-xs">
                                      {formatTime(block.start_time)}
                                    </span>
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="flex items-start justify-between gap-2">
                                      <h4 className="font-semibold text-white group-hover:text-purple-200 transition-colors">{block.activity.name}</h4>
                                      <span className="text-purple-300 font-medium text-sm shrink-0">
                                        {formatPriceWithRmb(block.activity.cost)}
                                      </span>
                                    </div>
                                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                      <span className={`text-xs px-2 py-0.5 rounded-full text-white/90 ${dotColor}/30 border border-white/10`}>
                                        {getCategoryLabel(block.activity.category)}
                                      </span>
                                      <span className="text-xs text-gray-500">⏱ {block.activity.duration} 分钟</span>
                                      <span className="text-xs text-yellow-400">⭐ {block.activity.rating.toFixed(1)}</span>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        {/* Refine with AI */}
                        <div className="mt-6 glass-card rounded-2xl p-5 border border-purple-500/20">
                          <h3 className="text-base font-bold text-white mb-1">🔧 AI 微调行程</h3>
                          <p className="text-gray-400 text-xs mb-3">告诉 AI 你希望如何调整 {cityPlan.city_name} 的安排。</p>
                          <div className="flex gap-2">
                            <input
                              type="text"
                              value={refineMessage[cityPlan.city_id] ?? ""}
                              onChange={(e) => setRefineMessage(prev => ({ ...prev, [cityPlan.city_id]: e.target.value }))}
                              onKeyDown={(e) => e.key === "Enter" && !isRefining[cityPlan.city_id] && handleRefineCity(cityPlan)}
                              placeholder={`例如："把博物馆换成夜生活" 或 "第 1 天加一顿美食"`}
                              className="flex-1 bg-gray-800/60 border border-gray-600 text-white rounded-lg px-3 py-2 text-sm placeholder-gray-500 focus:outline-none focus:border-purple-500"
                              disabled={!!isRefining[cityPlan.city_id]}
                            />
                            <button
                              onClick={() => handleRefineCity(cityPlan)}
                              disabled={!!isRefining[cityPlan.city_id] || !refineMessage[cityPlan.city_id]?.trim()}
                              className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-40 text-sm whitespace-nowrap"
                            >
                              {isRefining[cityPlan.city_id] ? "调整中..." : "应用修改"}
                            </button>
                          </div>
                          {refineResult[cityPlan.city_id] && (
                            <div className={`mt-3 text-sm px-4 py-3 rounded-lg ${refineResult[cityPlan.city_id]?.startsWith("暂时无法") || refineResult[cityPlan.city_id]?.startsWith("请求失败") ? "bg-red-900/30 text-red-300" : "bg-purple-900/30 text-purple-200"}`}>
                              {refineResult[cityPlan.city_id]}
                            </div>
                          )}
                          <div className="flex flex-wrap gap-2 mt-3">
                            {["安排更多美食", "最后一天增加夜生活", "移除最贵的活动", "换成户外活动"].map((suggestion) => (
                              <button
                                key={suggestion}
                                onClick={() => setRefineMessage(prev => ({ ...prev, [cityPlan.city_id]: suggestion }))}
                                className="text-xs px-3 py-1.5 bg-gray-700/60 text-gray-300 rounded-full hover:bg-gray-600/60 transition-colors"
                              >
                                {suggestion}
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}

      {/* Activity Modal */}
      {selectedActivity && (
        <ActivityModal
          activity={selectedActivity}
          onClose={() => setSelectedActivity(null)}
        />
      )}
    </div>
  );
}
