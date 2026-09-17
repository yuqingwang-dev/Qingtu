"use client";

import { useState, useEffect } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { DayRouteSummary } from "../../lib/routeTypes";
import {
  getLocalizedDescription,
  getLocalizedPlaceName,
} from "../../lib/locale";

const GoogleItineraryMap = dynamic(() => import("../../components/GoogleItineraryMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-96 bg-gray-100 rounded-lg flex items-center justify-center">
      <p className="text-gray-500">地图加载中…</p>
    </div>
  ),
});

interface ActivitySummary {
  id: number;
  name: string;
  name_zh?: string | null;
  category: string;
  cost: number;
  duration: number;
  rating: number;
  poi_source?: { rating_known?: boolean } | null;
  coordinates: {
    latitude: number;
    longitude: number;
  };
  tags?: string[] | null;
  description?: string | null;
  description_zh?: string | null;
}

interface ItineraryBlock {
  start_time: string;
  end_time: string;
  activity: ActivitySummary;
  travel_time_from_previous?: number;
  notes?: string;
}

interface ItineraryDay {
  route_summary?: DayRouteSummary | null;
  date: string;
  city_id?: number;
  city_name?: string;
  total_cost: number;
  total_duration_minutes: number;
  blocks: ItineraryBlock[];
}

interface SharedItinerary {
  id: string;
  created_at: string;
  view_count: number;
  trip_preferences: {
    start_date: string;
    end_date: string;
    destination_city_id?: number;
    city_segments?: Array<{
      city_id: number;
      stay_duration_days: number;
    }>;
  };
  itinerary: {
    days: ItineraryDay[];
    summary: {
      total_cost: number;
      avg_cost_per_day: number;
      categories_covered: string[];
      pace_label: string;
    };
    narrative?: {
      narrative_text: string;
      explanations?: string;
      tips?: string;
    };
  };
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SharePage() {
  const params = useParams();
  const token = params.token as string;
  const [itinerary, setItinerary] = useState<SharedItinerary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token) {
      fetchSharedItinerary();
    }
  }, [token]);

  const fetchSharedItinerary = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/share/${token}`);
      if (!response.ok) {
        throw new Error("行程不存在或已取消分享");
      }
      const data = await response.json();
      setItinerary(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("zh-CN", {
      weekday: "long",
      month: "long",
      day: "numeric",
      year: "numeric",
    });
  };

  const formatTime = (timeStr: string) => {
    return new Date(timeStr).toLocaleTimeString("zh-CN", { hour: "numeric", minute: "2-digit", hour12: false });
  };

  const getCategoryColor = (category: string) => {
    const colors: { [key: string]: string } = {
      food: "bg-emerald-100 text-emerald-700",
      culture: "bg-purple-100 text-purple-700",
      nightlife: "bg-pink-100 text-pink-700",
      nature: "bg-green-100 text-green-700",
      shopping: "bg-amber-100 text-amber-700",
      adventure: "bg-red-100 text-red-700",
      beaches: "bg-cyan-100 text-cyan-700",
    };
    return colors[category.toLowerCase()] || "bg-blue-100 text-blue-700";
  };

  if (loading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-t-2 border-b-2 border-purple-300 mx-auto mb-4"></div>
          <p className="text-white text-xl">正在打开分享的旅程…</p>
        </div>
      </div>
    );
  }

  if (error || !itinerary) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center p-6">
        <div className="glass-card rounded-2xl p-12 text-center max-w-md">
          <div className="text-6xl mb-6">🔒</div>
          <h1 className="text-3xl font-bold text-white mb-4">暂时找不到这份行程</h1>
          <p className="text-gray-300 mb-8">
            {error || "这份行程不存在，或分享者已将它设为私密。"}
          </p>
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-semibold hover:opacity-90 transition-opacity"
          >
            规划我的旅行
          </Link>
        </div>
      </div>
    );
  }

  const isMultiCity = (itinerary.trip_preferences.city_segments?.length ?? 0) > 1;
  const cityNames = isMultiCity
    ? [...new Set(itinerary.itinerary.days.map(d => d.city_name).filter(Boolean))].join(", ")
    : "分享的晴途行程";

  return (
    <div className="min-h-screen gradient-bg">
      <div className="container mx-auto px-4 py-8 pt-24">
        {/* Header */}
        <div className="glass-card rounded-2xl p-8 mb-6">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <h1 className="text-3xl font-bold gradient-text">
                  {isMultiCity ? `多城市旅行： ${cityNames}` : cityNames}
                </h1>
                <span className="px-3 py-1 bg-green-500/20 text-green-300 rounded-full text-sm font-medium">
                  Public
                </span>
              </div>
              <p className="text-gray-300">
                {itinerary.itinerary.days.length} 天 · {itinerary.itinerary.summary.total_cost.toFixed(0)}（原币参考） •
                {" "}{itinerary.view_count} {itinerary.view_count === 1 ? "view" : "views"}
              </p>
            </div>
            <Link
              href="/"
              className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-semibold hover:opacity-90 transition-opacity"
            >
              规划我的旅行
            </Link>
          </div>
        </div>

        {/* AI Narrative */}
        {itinerary.itinerary.narrative?.narrative_text && (
          <div className="glass-card rounded-2xl p-6 mb-6">
            <h3 className="text-xl font-bold text-white mb-3">✨ 旅程小贴士</h3>
            <p className="text-gray-300 leading-relaxed whitespace-pre-line mb-4">
              {itinerary.itinerary.narrative.narrative_text}
            </p>
            {itinerary.itinerary.narrative.explanations && (
              <p className="text-gray-400 text-sm leading-relaxed whitespace-pre-line mb-4">
                {itinerary.itinerary.narrative.explanations}
              </p>
            )}
            {itinerary.itinerary.narrative.tips && (
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                <p className="text-blue-300 text-sm leading-relaxed whitespace-pre-line">
                  💡 <strong>出行提醒：</strong> {itinerary.itinerary.narrative.tips}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="glass-card rounded-xl p-4">
            <p className="text-gray-400 text-sm mb-1">费用参考</p>
            <p className="text-2xl font-bold text-white">
              ${itinerary.itinerary.summary.total_cost.toFixed(0)}
            </p>
          </div>
          <div className="glass-card rounded-xl p-4">
            <p className="text-gray-400 text-sm mb-1">每天参考</p>
            <p className="text-2xl font-bold text-white">
              ${itinerary.itinerary.summary.avg_cost_per_day.toFixed(0)}
            </p>
          </div>
          <div className="glass-card rounded-xl p-4">
            <p className="text-gray-400 text-sm mb-1">旅行节奏</p>
            <p className="text-2xl font-bold text-white capitalize">
              {itinerary.itinerary.summary.pace_label}
            </p>
          </div>
        </div>

        {/* Daily Itinerary */}
        <div className="space-y-6">
          {itinerary.itinerary.days.map((day, dayIndex) => (
            <div key={dayIndex} className="glass-card rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-xl font-bold text-white">
                    Day {dayIndex + 1}
                    {day.city_name && ` - ${day.city_name}`}
                  </h3>
                  <p className="text-gray-400">{formatDate(day.date)}</p>
                </div>
                <span className="text-purple-300 font-semibold">
                  ${day.total_cost.toFixed(0)}
                </span>
              </div>

              {/* Google Map */}
              <div className="mb-6">
                <GoogleItineraryMap activities={day.blocks.map(block => block.activity)} routeSummary={day.route_summary} />
              </div>

              {/* Activity Timeline */}
              <div className="space-y-3">
                {day.blocks.map((block, blockIndex) => {
                  const localizedName = getLocalizedPlaceName(
                    block.activity.name,
                    block.activity.name_zh
                  );
                  const localizedDescription = getLocalizedDescription(
                    block.activity.description,
                    block.activity.description_zh
                  );

                  return (
                  <div key={blockIndex} className="flex gap-4">
                    <div className="flex-shrink-0 w-20 text-right">
                      <p className="text-sm font-medium text-purple-300">
                        {formatTime(block.start_time)}
                      </p>
                      {block.travel_time_from_previous && (
                        <p className="text-xs text-gray-500">
                          +{block.travel_time_from_previous}m
                        </p>
                      )}
                    </div>
                    <div className="flex-1 bg-white/5 hover:bg-white/10 rounded-lg p-4 transition-colors">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <h4 className="font-semibold text-white">
                              {localizedName}
                            </h4>
                            <span className={`px-2 py-1 rounded text-xs font-medium ${getCategoryColor(block.activity.category)}`}>
                              {block.activity.category}
                            </span>
                          </div>
                          {localizedDescription && (
                            <p className="text-sm text-gray-400 mb-2">
                              {localizedDescription}
                            </p>
                          )}
                          <div className="flex items-center gap-4 text-sm text-gray-400">
                            <span>{block.activity.poi_source?.rating_known === false ? "暂无评分" : `⭐ ${block.activity.rating.toFixed(1)}`}</span>
                            <span>⏱️ {block.activity.duration} min</span>
                            <span>💰 ${block.activity.cost}</span>
                          </div>
                          {block.notes && (
                            <p className="text-sm text-blue-300 mt-2">
                              💡 {block.notes}
                            </p>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>

        {/* Footer CTA */}
        <div className="glass-card rounded-2xl p-8 mt-8 text-center">
          <h3 className="text-2xl font-bold text-white mb-3">
            Love this itinerary?
          </h3>
          <p className="text-gray-300 mb-6">
            用晴途 Qingtu，安排你的下一次出发
          </p>
          <Link
            href="/"
            className="inline-block px-8 py-4 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-semibold hover:opacity-90 transition-opacity text-lg"
          >
            Start Planning Your Trip
          </Link>
        </div>
      </div>
    </div>
  );
}
