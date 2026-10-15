"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession, signIn } from "next-auth/react";
import dynamic from "next/dynamic";
import Toast from "../../components/Toast";
import DestinationPicker from "../../components/DestinationPicker";
import ActivityModal from "../../components/ActivityModal";
import TravelKnowledge from "../../components/TravelKnowledge";
import { api } from "../../lib/api";
import { getSessionId } from "../../lib/session";
import { useItineraryStore } from "../../store/itineraryStore";
import type { LodgingLocation, DayRouteSummary, RouteReport } from "../../lib/routeTypes";
import {
  formatChineseDate,
  formatChineseShortDate,
  formatChineseTime,
  formatChineseWeekday,
  formatPriceWithRmb,
  getCategoryLabel,
  getLocalizedCityName,
  getLocalizedDescription,
  getLocalizedPlaceName,
  getLocalizedSelectionReason,
} from "../../lib/locale";

// Dynamic imports to avoid SSR issues
const GoogleItineraryMap = dynamic(() => import("../../components/GoogleItineraryMap"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-96 bg-gray-100 rounded-lg flex items-center justify-center">
      <p className="text-gray-500">地图加载中...</p>
    </div>
  ),
});

const WorldMapSelector = dynamic(() => import("@/components/WorldMapSelector"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-96 glass-card rounded-lg flex items-center justify-center">
      <p className="text-gray-300">城市地图加载中...</p>
    </div>
  ),
});

interface City {
  id: number;
  name: string;
  name_zh?: string | null;
  country: string;
  country_zh?: string | null;
  time_zone: string;
  default_currency: string;
  latitude?: number | null;
  longitude?: number | null;
  is_domestic?: boolean;
  supports_real_routes?: boolean;
}

interface TripPreferences {
  use_real_routes?: boolean;
  lodging?: LodgingLocation;
  daily_start_time?: string;
  daily_end_time?: string;
  return_to_lodging?: boolean;
  start_date: string;
  end_date: string;
  destination_city_id: number;
  trip_type: "day_trip" | "weekend" | "one_week" | "long";
  budget_level: "low" | "medium" | "high";
  budget_per_day?: number;
  preferred_categories: string[];
  energy_level: "relaxed" | "moderate" | "active";
  travel_mode: "walking" | "public_transport" | "taxi" | "self_drive" | "mixed";
  constraints?: {
    must_visit?: string[];
    avoid?: string[];
    dietary_preferences?: string;
    walking_tolerance?: "low" | "medium" | "high";
  };
}

interface VenueAlternative {
  name: string;
  category: string;
  rating: number;
  address: string;
  latitude: number;
  longitude: number;
  cost: number;
  price_label: string;
  place_id: string;
  source: string;
}

interface SelectionExplanation {
  category_match: boolean;
  budget_fit: string;
  time_fit: string;
  travel_proximity: string;
  rating_quality: string;
  must_visit: boolean;
  summary: string;
  semantic_relevance_score?: number | null;
}

interface ActivitySummary {
  id: number;
  name: string;
  name_zh?: string | null;
  category: string;
  cost: number;
  duration: number;
  rating: number;
  poi_source?: { provider?: string; provider_poi_id?: string; observed_at?: string; address?: string; rating_known?: boolean; cost_kind?: string; coordinate_system?: string } | null;
  coordinates: {
    latitude: number;
    longitude: number;
  };
  tags?: string[] | null;
  description?: string | null;
  description_zh?: string | null;
  explanation?: SelectionExplanation | null;
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
  total_cost: number;
  total_duration_minutes: number;
  blocks: ItineraryBlock[];
}

interface ItineraryResponse {
  route_report?: RouteReport | null;
  poi_search?: { status: string; provider?: string; fetched_count: number; candidate_count: number; cache_hit: boolean; warnings: string[] } | null;
  days: ItineraryDay[];
  summary: {
    total_cost: number;
    avg_cost_per_day: number;
    categories_covered: string[];
    pace_label: string;
  };
  optimization_score: number;
  confidence_score: number;
  narrative: {
    narrative_text: string;
    explanations?: string;
    tips?: string;
    source?: string;
    provider?: string;
  };
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AgentPlanResult {
  itinerary: ItineraryResponse;
  candidate_ids: number[];
  termination_reason: string;
  agent_trace: { tool_name: string; status: string; candidate_ids: number[] }[];
}

const TOOL_LABELS: Record<string, string> = {
  search_activities_semantic: "查找候选景点",
  filter_activities: "筛选符合条件的景点",
  estimate_travel_time: "估算交通时间",
  explain_activity: "记录选择依据",
  optimize_itinerary: "安排每天行程",
};

const CATEGORIES = [
  "food",
  "culture",
  "nightlife",
  "nature",
  "shopping",
  "adventure",
  "beaches",
] as const;

interface ToastState {
  message: string;
  type: "error" | "success" | "info";
}

type Step = "select-city" | "preferences" | "result";

function LoadingProgress({ cityName, agentMode = false, routeMode = false }: { cityName?: string; agentMode?: boolean; routeMode?: boolean }) {
  return <div className="qt-loader" role="status" aria-live="polite">
    <span className="qt-spinner" aria-hidden="true" />
    <h2>正在整理{cityName ? `你的${cityName}之旅` : "你的旅程"}</h2>
    <p>{routeMode ? "正在查询地点与交通。首次规划可能需要 1–3 分钟，请稍候。" : agentMode ? "正在按你的喜好筛选地点，再安排每天的顺序。" : "正在结合日期、预算和喜好安排行程，请稍候。"}</p>
    <p>生成完成后会自动展示结果，不用重复点击。</p>
  </div>;
}

export default function SingleCityPlanner() {
  const router = useRouter();
  const { data: session } = useSession();
  const [currentStep, setCurrentStep] = useState<Step>("select-city");
  const [cities, setCities] = useState<City[]>([]);
  const [cityScope, setCityScope] = useState<"domestic" | "international" | "all">("domestic");
  const [citiesLoading, setCitiesLoading] = useState(true);
  const [citiesError, setCitiesError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [itinerary, setItinerary] = useState<ItineraryResponse | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [selectedActivity, setSelectedActivity] = useState<ActivitySummary | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [refineMessage, setRefineMessage] = useState("");
  const [isRefining, setIsRefining] = useState(false);
  const [refineResult, setRefineResult] = useState<string | null>(null);
  const [refineAlternatives, setRefineAlternatives] = useState<VenueAlternative[] | null>(null);
  const [activeDayIndex, setActiveDayIndex] = useState(0);
  const [agentMode, setAgentMode] = useState(false);
  const [agentMessage, setAgentMessage] = useState("");
  const [agentResult, setAgentResult] = useState<AgentPlanResult | null>(null);
  const [lodgingQuery, setLodgingQuery] = useState("");
  const [lodgingResults, setLodgingResults] = useState<LodgingLocation[]>([]);
  const [lodgingLoading, setLodgingLoading] = useState(false);
  const [formData, setFormData] = useState<Partial<TripPreferences>>({
    trip_type: "weekend",
    budget_level: "medium",
    energy_level: "moderate",
    travel_mode: "mixed",
    preferred_categories: [],
  });

  // Zustand store
  const { setCurrentSavedId } = useItineraryStore();

  useEffect(() => {
    fetchCities();
  }, []);

  const fetchCities = async () => {
    setCitiesLoading(true);
    setCitiesError(false);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/cities`);
      if (!response.ok) throw new Error(`City request failed: ${response.status}`);
      const data: City[] = await response.json();
      setCities(data);
      const requestedCity = new URLSearchParams(window.location.search).get("city");
      const initialCity = data.find(city => city.name === requestedCity);
      if (initialCity) {
        setFormData(current => ({ ...current, destination_city_id: initialCity.id }));
        setCityScope(initialCity.is_domestic ? "domestic" : "international");
        setCurrentStep("preferences");
      }
    } catch (error) {
      console.error("Failed to fetch cities:", error);
      setCitiesError(true);
    } finally {
      setCitiesLoading(false);
    }
  };

  const handleCitySelect = (cityId: number) => {
    setFormData({ ...formData, destination_city_id: cityId, lodging: undefined, use_real_routes: false });
    setLodgingQuery("");
    setLodgingResults([]);
  };

  const searchLodging = async () => {
    if (!lodgingQuery.trim() || !formData.destination_city_id) return;
    setLodgingLoading(true);
    setLodgingResults([]);
    try {
      const params = new URLSearchParams({ city_id: String(formData.destination_city_id), keywords: lodgingQuery.trim(), limit: "5" });
      const response = await fetch(`${API_BASE_URL}/api/v1/domestic/pois?${params}`);
      const data = await response.json();
      if (!response.ok || data.errors?.length) throw new Error(data.errors?.[0]?.message || data.detail || "住宿搜索失败");
      const results: LodgingLocation[] = data.data.filter((poi: any) => poi.latitude != null && poi.longitude != null).map((poi: any) => ({
        name: poi.name, city_id: formData.destination_city_id!, latitude: poi.latitude, longitude: poi.longitude,
        provider_poi_id: poi.identifier.provider_poi_id, coordinate_system: "GCJ02",
      }));
      setLodgingResults(results);
      if (!results.length) setToast({ message: "没有找到地点，请输入更完整的酒店名或附近地标。", type: "info" });
    } catch (error) {
      setToast({ message: error instanceof Error ? error.message : "住宿搜索失败", type: "error" });
    } finally { setLodgingLoading(false); }
  };

  const handleCityDeselect = () => {
    setFormData({ ...formData, destination_city_id: undefined });
  };

  const handleCityConfirm = (_cityId: number) => {
    setCurrentStep("preferences");
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (formData.use_real_routes && !formData.lodging) {
      setToast({ message: "请先搜索并选择具体的住宿或出发地点。", type: "info" });
      return;
    }
    setLoading(true);
    setItinerary(null);
    setAgentResult(null);

    try {
      const destination = cities.find(city => city.id === formData.destination_city_id);
      if (!destination) {
        setToast({ message: "请先选择目的地城市。", type: "error" });
        return;
      }
      const planEndpoint = agentMode ? "/agent-plan" : destination.is_domestic ? "/domestic/plan" : "/plan-itinerary";
      const authToken = (session as any)?.accessToken;
      const response = await fetch(`${API_BASE_URL}/api/v1${planEndpoint}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-ID": getSessionId(),
          ...(authToken ? { "Authorization": `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify(agentMode ? { preferences: formData, user_message: agentMessage.trim() || undefined } : formData),
      });

      if (!response.ok) {
        const error = await response.json();
        let errorMessage = "暂时无法生成行程，请稍后再试";

        if (error.detail) {
          if (typeof error.detail === "string") {
            errorMessage = error.detail;
          } else if (error.detail.message) {
            errorMessage = error.detail.message;
            if (error.detail.error_code === "INFEASIBLE_CONSTRAINTS" && error.detail.details) {
              const infeasible = Object.entries(error.detail.details)
                .map(([name, reason]) => `${name}: ${reason}`)
                .join(", ");
              errorMessage += ` (${infeasible})`;
            }
          }
          else if (Array.isArray(error.detail)) {
            errorMessage = error.detail.map((item: { msg: string }) => item.msg).join("；");
          }
        }

        setToast({ message: errorMessage, type: "error" });
        return;
      }

      const data = await response.json();
      setItinerary(agentMode ? data.itinerary : data);
      setAgentResult(agentMode ? data : null);
      setActiveDayIndex(0);
      setCurrentStep("result");
      const planned: ItineraryResponse = agentMode ? data.itinerary : data;
      const emptyDays = planned.days.filter(day => day.blocks.length === 0).length;
      setToast(emptyDays
        ? { message: `已生成部分安排，${emptyDays} 天待补充，请查看原因或调整条件。`, type: "info" }
        : { message: "行程生成成功！", type: "success" });
    } catch (error) {
      console.error("Error generating itinerary:", error);
      setToast({
        message: "网络异常，请检查连接后重试。",
        type: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  const toggleCategory = (category: string) => {
    const current = formData.preferred_categories || [];
    if (current.includes(category)) {
      setFormData({
        ...formData,
        preferred_categories: current.filter((c) => c !== category),
      });
    } else {
      setFormData({
        ...formData,
        preferred_categories: [...current, category],
      });
    }
  };

  const handleRefine = async () => {
    if (!itinerary || !refineMessage.trim() || !formData) return;
    setIsRefining(true);
    setRefineResult(null);
    setRefineAlternatives(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/refine-itinerary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          itinerary,
          preferences: {
            ...formData,
            start_date: formData.start_date,
            end_date: formData.end_date,
          },
          user_message: refineMessage,
        }),
      });
      if (response.ok) {
        const data = await response.json();
        setItinerary(data.itinerary);
        setActiveDayIndex(0);
        setRefineResult(data.assistant_message);
        setRefineAlternatives(data.alternatives || null);
        setRefineMessage("");
      } else {
        const err = await response.json();
        setRefineResult(`暂时无法应用修改：${typeof err.detail === "string" ? err.detail : err.detail?.message || "未知错误"}`);
      }
    } catch (e) {
      setRefineResult("请求失败，请确认后端是否已启动。");
    } finally {
      setIsRefining(false);
    }
  };

  const handleShareItinerary = async () => {
    if (!itinerary) return;

    // Must be saved first before sharing
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
      // First save the itinerary as public
      const authToken = (session as any)?.accessToken;

      const saveRequest = {
        trip_preferences: {
          ...formData,
          start_date: formData.start_date,
          end_date: formData.end_date,
          destination_city_id: formData.destination_city_id,
          trip_type: formData.trip_type,
          budget_level: formData.budget_level,
          budget_per_day: formData.budget_per_day,
          preferred_categories: formData.preferred_categories || [],
          energy_level: formData.energy_level,
          travel_mode: formData.travel_mode,
          constraints: formData.constraints
        },
        itinerary: itinerary,
        is_public: true // Make it public for sharing
      };

      const savedItinerary = await api.saveItinerary(saveRequest, authToken);

      if (savedItinerary.share_url) {
        setShareUrl(savedItinerary.share_url);
        // Copy to clipboard
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
    if (!itinerary) return;

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

      // Build the complete request matching backend schema
      const saveRequest = {
        trip_preferences: {
          ...formData,
          start_date: formData.start_date,
          end_date: formData.end_date,
          destination_city_id: formData.destination_city_id,
          trip_type: formData.trip_type,
          budget_level: formData.budget_level,
          budget_per_day: formData.budget_per_day,
          preferred_categories: formData.preferred_categories || [],
          energy_level: formData.energy_level,
          travel_mode: formData.travel_mode,
          constraints: formData.constraints
        },
        itinerary: itinerary,
        is_public: false
      };

      console.log("Saving itinerary with request:", JSON.stringify(saveRequest, null, 2));

      const savedId = await api.saveItinerary(saveRequest, authToken);

      setCurrentSavedId(savedId.id);
      setToast({ message: "行程已成功保存！", type: "success" });

      // Redirect to My Itineraries after successful save
      setTimeout(() => router.push("/my-itineraries"), 1500);
    } catch (error) {
      console.error("Save itinerary error:", error);
      setToast({ message: "保存行程失败", type: "error" });
    } finally {
      setIsSaving(false);
    }
  };

  const selectedCity = cities.find(c => c.id === formData.destination_city_id);
  const tripLength = formData.start_date && formData.end_date
    ? Math.floor((Date.parse(formData.end_date) - Date.parse(formData.start_date)) / 86400000) + 1 : 0;
  const domesticCount = cities.filter(city => city.is_domestic).length;
  const visibleCities = cities.filter(city =>
    cityScope === "all" || (cityScope === "domestic" ? city.is_domestic : !city.is_domestic)
  );
  const selectedCityDisplayName = selectedCity
    ? getLocalizedCityName(selectedCity.name, selectedCity.name_zh)
    : undefined;

  const formatTime = (timeStr: string) => formatChineseTime(timeStr);

  return (
    <div className="qt-planner min-h-screen gradient-bg py-8 px-4 pt-20">
      <div className="max-w-7xl mx-auto">
        {!session && <div className="qt-login-notice"><span>先安心规划，喜欢的行程登录后就能保存。</span><button type="button" onClick={() => signIn("google")}>登录保存</button></div>}
        <div className="qt-planner-heading"><div><p className="qt-eyebrow">晴途 · 一城一段好时光</p>
          <h1>{currentStep === "select-city" ? "你的下一次出发，从这里开始。" : currentStep === "preferences" ? `把${selectedCityDisplayName || "这次旅行"}，安排成喜欢的样子。` : "你的出游手账，准备好了。"}</h1>
          <p>{currentStep === "select-city" ? "先选目的地，不用做功课也能开始。" : currentStep === "preferences" ? "先填写日期和喜好，其他选项可以慢慢来。" : "点选日期查看每天安排，信息来源和估算会分别说明。"}</p></div>
          <button type="button" onClick={() => router.push("/")} className="qt-text-link">← 返回首页</button>
        </div>
        <ol className="qt-steps" aria-label="规划步骤">
          {([{id:"select-city",label:"选城市"},{id:"preferences",label:"定偏好"},{id:"result",label:"看行程"}] as const).map((step,index) =>
            <li key={step.id} aria-current={currentStep === step.id ? "step" : undefined}><span className="qt-step-number">{index+1}</span><span>{step.label}</span></li>
          )}
        </ol>

        {/* Step 1: City Selection */}
        {currentStep === "select-city" && (
          <div>
            <div className="flex flex-wrap justify-center gap-3 mb-3" role="group" aria-label="目的地区域">
              {([
                { value: "domestic", label: "国内", count: domesticCount },
                { value: "international", label: "国外", count: cities.length - domesticCount },
                { value: "all", label: "全部", count: cities.length },
              ] as const).map(scope => (
                <button
                  key={scope.value}
                  type="button"
                  aria-pressed={cityScope === scope.value}
                  onClick={() => {
                    if (cityScope !== scope.value) {
                      setCityScope(scope.value);
                      handleCityDeselect();
                    }
                  }}
                  className={`px-5 py-2 rounded-lg transition-colors ${cityScope === scope.value
                    ? "bg-purple-600 text-white"
                    : "glass-card text-gray-200 hover:bg-purple-500/20"}`}
                >
                  {scope.label}{!citiesLoading && !citiesError ? `（${scope.count}）` : ""}
                </button>
              ))}
            </div>
            <p className="text-center text-sm text-gray-300 mb-5">
              国内四城可查询真实地点与交通；国外城市提供基础规划。选择卡片后点击“下一步”。
            </p>
            {citiesLoading ? (
              <p role="status" className="text-center text-gray-300 py-12">正在加载城市...</p>
            ) : citiesError ? (
              <div role="alert" className="text-center text-gray-300 py-12">
                <p>城市列表加载失败，请确认后端服务可用后重试。</p>
                <button type="button" onClick={fetchCities} className="mt-3 px-4 py-2 rounded-lg bg-purple-600 text-white">重新加载</button>
              </div>
            ) : visibleCities.length === 0 ? (
              <p className="text-center text-gray-300 py-12">当前区域暂未收录城市，请切换其他区域。</p>
            ) : (
              <>
                <DestinationPicker cities={visibleCities} selectedId={formData.destination_city_id} onSelect={handleCitySelect} onConfirm={handleCityConfirm} />
                <details className="qt-map-option"><summary>想从地图上选？展开地图（可选）</summary>
              <div className="h-[460px]">
                <WorldMapSelector
                  key={cityScope}
                  cities={visibleCities}
                  selectedCities={formData.destination_city_id ? [formData.destination_city_id] : []}
                  onCitySelect={handleCitySelect}
                  onConfirm={handleCityConfirm}
                  onDeselect={handleCityDeselect}
                  multiSelect={false}
                  title={cityScope === "domestic" ? "选择你的国内目的地" : cityScope === "international" ? "选择你的国外目的地" : "选择你的目的地"}
                />
              </div>

                </details>
              </>
            )}
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <LoadingProgress cityName={selectedCityDisplayName} agentMode={agentMode} routeMode={formData.use_real_routes} />
        )}

        {/* Step 2: Preferences Form */}
        {currentStep === "preferences" && !loading && (
          <div className="glass-card rounded-2xl p-8">
            <div className="mb-6">
              <h2 className="text-2xl font-bold gradient-text mb-2">
                规划你的 {selectedCityDisplayName} 之旅
              </h2>
              <p className="text-gray-300">
                📍 {selectedCity?.country_zh || selectedCity?.country} • {selectedCity?.default_currency}
              </p>
              <button
                onClick={() => setCurrentStep("select-city")}
                className="text-purple-400 hover:text-purple-300 text-sm mt-2"
              >
                ← 重新选择目的地
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Trip Dates */}
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    开始日期
                  </label>
                  <input
                    type="date"
                    required
                    className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                    aria-label="开始日期" value={formData.start_date || ""}
                    onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    结束日期
                  </label>
                  <input
                    type="date"
                    required
                    className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                    min={formData.start_date || undefined} aria-label="结束日期" value={formData.end_date || ""}
                    onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                  />
                </div>
              </div>

              {/* Trip Type */}
              {tripLength > 0 && <p className="text-sm text-gray-400" role="status">这次共 {tripLength} 天，包含开始和结束当天。</p>}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  旅行类型
                </label>
                <select
                  className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  aria-label="旅行类型" value={formData.trip_type}
                  onChange={(e) => setFormData({ ...formData, trip_type: e.target.value as any })}
                >
                  <option value="day_trip">一天走走</option>
                  <option value="weekend">周末短途</option>
                  <option value="one_week">一周旅行</option>
                  <option value="long">慢慢住几天</option>
                </select>
              </div>

              {/* Budget */}
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    预算等级
                  </label>
                  <select
                    className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                    aria-label="预算等级" value={formData.budget_level}
                    onChange={(e) => setFormData({ ...formData, budget_level: e.target.value as any })}
                  >
                    <option value="low">经济一点</option>
                    <option value="medium">舒适适中</option>
                    <option value="high">预算宽裕</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    每日预算 ({selectedCity?.default_currency})
                  </label>
                  <input
                    type="number"
                    placeholder="可选"
                    className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                    aria-label="每日景点和体验预算" value={formData.budget_per_day ?? ""}
                    onChange={(e) => setFormData({ ...formData, budget_per_day: Number(e.target.value) })}
                  />
                  <p className="text-xs text-gray-400 mt-2">景点和体验费用参考，不含住宿与交通。</p>
                </div>
              </div>

              {/* Energy Level & Travel Mode */}
              <div className="grid md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    行程节奏
                  </label>
                  <select
                    className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                    aria-label="旅行节奏" value={formData.energy_level}
                    onChange={(e) => setFormData({ ...formData, energy_level: e.target.value as any })}
                  >
                    <option value="relaxed">轻松一点 · 留些休息时间</option>
                    <option value="moderate">刚刚好 · 玩与休息兼顾</option>
                    <option value="active">多逛一些 · 安排更充实</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    出行方式
                  </label>
                  <select
                    className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                    aria-label="出行方式" value={formData.travel_mode}
                    onChange={(e) => setFormData({ ...formData, travel_mode: e.target.value as any })}
                  >
                    <option value="walking">步行为主</option>
                    <option value="public_transport">地铁与公交</option>
                    <option value="taxi">打车出行</option>
                    <option value="self_drive">自己开车</option>
                    <option value="mixed">灵活搭配</option>
                  </select>
                </div>
              </div>

              {/* Categories */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">
                  偏好类别
                </label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((category) => (
                    <button
                      key={category}
                      type="button"
                      onClick={() => toggleCategory(category)}
                      aria-pressed={!!formData.preferred_categories?.includes(category)}
                      className={`px-4 py-2 rounded-lg transition-all ${
                        formData.preferred_categories?.includes(category)
                          ? "bg-gradient-to-r from-purple-500 to-pink-500 text-white"
                          : "bg-gray-800/50 text-gray-300 hover:bg-gray-700/50"
                      }`}
                    >
                      {getCategoryLabel(category)}
                    </button>
                  ))}
                </div>
              </div>

              <details className="qt-option-section" open={formData.use_real_routes || agentMode || undefined}>
                <summary>更多安排：住宿路线与智能筛选（可选）</summary>
                <p className="text-sm text-gray-400 mb-4">第一次使用可以先跳过，直接生成基础行程。需要实际交通时，再选择住宿地点。</p>
                <div className="space-y-5">
              <div className="rounded-xl border border-purple-500/30 p-4 space-y-3">
                <label className="flex items-center gap-3 text-white cursor-pointer">
                  <input type="checkbox" checked={agentMode} onChange={e => setAgentMode(e.target.checked)} />
                  让 AI 帮我进一步筛选（可选）
                </label>
                <p className="text-sm text-gray-400">根据补充偏好查询和筛选已有景点，再安排行程；关闭时使用常规规划。</p>
                {agentMode && (
                  <div>
                    <label htmlFor="agent-preferences" className="block text-sm text-gray-300 mb-2">还有什么特别想玩的？</label>
                    <textarea id="agent-preferences" maxLength={2000} rows={3} value={agentMessage}
                      onChange={e => setAgentMessage(e.target.value)}
                      placeholder="例如：多安排文化景点，少购物，优先选择门票便宜的地方。"
                      className="w-full px-3 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white" />
                    <p className="text-xs text-gray-400 mt-2">当前基于已收录景点；真实道路导航、天气和预约查询将在后续加入。</p>
                  </div>
                )}
              </div>

              {selectedCity?.supports_real_routes && (
                <div className="rounded-xl border border-cyan-500/30 p-4 space-y-3">
                  <label className="flex items-center gap-3 text-white cursor-pointer">
                    <input type="checkbox" checked={!!formData.use_real_routes}
                      onChange={e => setFormData({ ...formData, use_real_routes: e.target.checked,
                        daily_start_time: formData.daily_start_time || "10:00", daily_end_time: formData.daily_end_time || "20:00",
                        return_to_lodging: formData.return_to_lodging ?? true })} />
                    加上住宿和真实交通 · {selectedCityDisplayName}
                  </label>
                  <p className="text-sm text-gray-400">首版支持 1–3 天、每天最多 3 个主要地点。查询交通时间后调整顺序与分天；未排入地点会说明原因。</p>
                  {formData.use_real_routes && <>
                    <label htmlFor="lodging-query" className="block text-sm text-gray-300">住宿或每日出发地点</label>
                    <div className="flex gap-2">
                      <input id="lodging-query" value={lodgingQuery} maxLength={80} placeholder="输入当前城市的酒店全名或附近地标"
                        onChange={e => { setLodgingQuery(e.target.value); setLodgingResults([]); setFormData({ ...formData, lodging: undefined }); }}
                        className="min-w-0 flex-1 px-3 py-2 bg-gray-800/50 border border-cyan-500/30 rounded-lg text-white" />
                      <button type="button" disabled={lodgingLoading || !lodgingQuery.trim()} onClick={searchLodging}
                        className="px-4 py-2 rounded-lg bg-cyan-700 text-white disabled:opacity-50">{lodgingLoading ? "搜索中" : "搜索"}</button>
                    </div>
                    <div className="space-y-1">{lodgingResults.map(place => (
                      <button type="button" key={place.provider_poi_id} onClick={() => { setFormData({ ...formData, lodging: place }); setLodgingQuery(place.name); setLodgingResults([]); }}
                        className="block w-full text-left rounded-lg p-2 text-white bg-white/5 hover:bg-cyan-800">{place.name}</button>
                    ))}</div>
                    <p className="text-sm text-cyan-300">{formData.lodging ? `已选择：${formData.lodging.name}` : "请从搜索结果中选择具体地点"}</p>
                    <div className="grid grid-cols-2 gap-3">
                      <label className="text-sm text-gray-300">每天出发时间<input type="time" required value={formData.daily_start_time || "10:00"}
                        onChange={e => setFormData({ ...formData, daily_start_time: e.target.value })} className="block w-full rounded-lg bg-gray-800 p-2 text-white" /></label>
                      <label className="text-sm text-gray-300">最晚结束/返回时间<input type="time" required value={formData.daily_end_time || "20:00"}
                        onChange={e => setFormData({ ...formData, daily_end_time: e.target.value })} className="block w-full rounded-lg bg-gray-800 p-2 text-white" /></label>
                    </div>
                    <label className="flex gap-2 text-gray-300 text-sm"><input type="checkbox" checked={formData.return_to_lodging ?? true}
                      onChange={e => setFormData({ ...formData, return_to_lodging: e.target.checked })} />每天返回住宿地点</label>
                    <p className="text-xs text-gray-400">采用下方选择的出行方式。“混合”按短途步行、长途公交查询；交通时间是方案参考，并非未来到达保证。</p>
                  </>}
                </div>
              )}


                </div>
              </details>
              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {loading ? "正在生成行程..." : "生成行程"}
              </button>
            </form>
          </div>
        )}

        {/* Step 3: Results */}
        {currentStep === "result" && itinerary && (
          <div className="space-y-6">
            {itinerary.days.some(day => day.blocks.length === 0) && (
              <div role="status" className="rounded-xl border border-amber-400/40 bg-amber-500/10 p-5 text-amber-100">
                <p className="font-semibold">行程尚未排满：{itinerary.days.filter(day => day.blocks.length === 0).length} 天待补充</p>
                <p className="text-sm mt-2">当前不重复且符合条件的景点不足，或受到预算、开放时间限制。没有安排的日期不是加载失败，也不代表当天没有费用。</p>
                <button type="button" onClick={() => setCurrentStep("preferences")} className="mt-3 underline">调整日期或放宽筛选条件，重新规划</button>
              </div>
            )}
            {/* Header with Save Button */}
            <div className="qt-result-heading glass-card rounded-2xl p-6 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-bold gradient-text">
                  {selectedCityDisplayName} 行程方案
                </h2>
                <p className="text-gray-300 mt-1">
                  共 {itinerary.days.length} 天 • 总预算 {formatPriceWithRmb(itinerary.summary.total_cost, selectedCity?.default_currency)}
                </p>
              </div>
              <div className="qt-result-actions flex gap-3">
                <button
                  onClick={() => {
                    setCurrentStep("preferences");
                    setItinerary(null);
                  }}
                  className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 transition-colors"
                >
                  修改计划
                </button>
                <button
                  onClick={handleShareItinerary}
                  disabled={isSharing}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50"
                >
                  {isSharing ? "分享中..." : "🔗 分享"}
                </button>
                <button
                  onClick={handleSaveItinerary}
                  disabled={isSaving}
                  className="px-6 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {isSaving ? "保存中..." : "保存行程"}
                </button>
              </div>
            </div>

            {agentResult && (
              <details className="glass-card rounded-2xl p-6 text-gray-300">
                <summary className="cursor-pointer text-white font-medium">查看智能筛选过程 · 最终候选 {agentResult.candidate_ids.length} 个</summary>
                {agentResult.termination_reason !== "optimized" && (
                  <p className="mt-3 text-sm text-amber-300">智能筛选提前结束，已使用当前候选地点完成常规排程。</p>
                )}
                <ol className="mt-4 space-y-2 list-decimal pl-5">
                  {agentResult.agent_trace.map((step, index) => (
                    <li key={index} className="text-sm">{TOOL_LABELS[step.tool_name] || "检查工具请求"}
                      {step.status === "error" ? "：条件未通过校验，保留原候选" : `：当前候选 ${step.candidate_ids.length} 个`}
                    </li>
                  ))}
                </ol>
              </details>
            )}

            {itinerary.poi_search?.provider === "amap" && (
              <div className="glass-card rounded-xl p-5 text-gray-300">
                <p className="font-medium text-white">{itinerary.poi_search.status === "fallback" ? "地点搜索暂不可用 · 使用已有资料" : `高德地点搜索${itinerary.poi_search.cache_hit ? "（缓存）" : ""} · 检索到 ${itinerary.poi_search.fetched_count} 个地点`}</p>
                <p className="text-sm mt-2">已去重并合并本地资料，共 {itinerary.poi_search.candidate_count} 个候选。地点和坐标来自搜索服务；费用、停留时长为参考估算，出行日期的营业时间及预约要求仍需核实。</p>
                {itinerary.poi_search.warnings.map((warning, i) => <p key={i} className="text-sm text-amber-300 mt-1">{warning}</p>)}
              </div>
            )}

            {itinerary.route_report && (
              <div className="glass-card rounded-xl p-5 text-gray-300">
                <h3 className="font-semibold text-white">交通规划结果 · {itinerary.route_report.status === "live" ? "高德路线方案" : "部分区间使用估算"}</h3>
                <p className="mt-2">全程交通约 {itinerary.route_report.optimized_travel_minutes} 分钟
                  {itinerary.route_report.saved_travel_minutes != null ? `；同一批地点原顺序约 ${itinerary.route_report.baseline_travel_minutes} 分钟，${itinerary.route_report.saved_travel_minutes >= 0 ? "减少" : "增加"} ${Math.abs(itinerary.route_report.saved_travel_minutes)} 分钟（同时检查时间窗）` : "；因地点集合变化，暂不比较优化前后的耗时"}</p>
                {itinerary.route_report.warnings.map((text, i) => <p key={i} className="text-sm text-amber-200 mt-2">{text}</p>)}
                {!!itinerary.route_report.unplanned.length && <details className="mt-3"><summary className="cursor-pointer">查看未安排地点</summary>
                  <ul className="mt-2 space-y-1">{itinerary.route_report.unplanned.map(item => <li key={item.id} className="text-sm">{item.name}：{item.reason}</li>)}</ul>
                </details>}
              </div>
            )}

            {/* AI Narrative */}
            {selectedCity && <TravelKnowledge
              cityId={selectedCity.id}
              cityName={selectedCity.name_zh || selectedCity.name}
              places={itinerary.days.flatMap(day => day.blocks.map(block => block.activity.name_zh || block.activity.name))}
              travelDate={itinerary.days[itinerary.days.length - 1]?.date}
            />}
            {itinerary.narrative?.narrative_text && (
              <>
              <div className='mb-3 flex items-center justify-between gap-3'>
                <span className={itinerary.narrative.source === 'ai' ? 'text-xs rounded-full px-3 py-1 bg-emerald-100 text-emerald-800' : 'text-xs rounded-full px-3 py-1 bg-amber-100 text-amber-900'}>
                  {itinerary.narrative.source === 'ai' ? 'AI 解读 · 已验证' : '规则降级 · 未生成 AI 解读'}
                </span>
                {itinerary.narrative.source !== 'ai' && <span className='text-sm text-amber-900'>行程仍可使用，但以下说明不是模型生成内容。</span>}
              </div>
              <div className="glass-card rounded-2xl p-6">
                <h3 className="text-xl font-bold text-white mb-3">这趟旅程的小贴士</h3>
                <p className="text-gray-300 leading-relaxed whitespace-pre-line">
                  {itinerary.narrative.narrative_text}
               </p>
               </div>
              </>
             )}

            {/* Refine Itinerary */}
            <div className="glass-card rounded-2xl p-6">
              <h3 className="text-lg font-bold text-white mb-1">想换个玩法？</h3>
              <p className="text-gray-400 text-sm mb-4">可以尝试用一句话调整行程。需要 AI 服务正常连接，失败时不会覆盖原安排。</p>
              <div className="flex gap-3">
                <input
                  type="text"
                  value={refineMessage}
                  onChange={(e) => setRefineMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !isRefining && handleRefine()}
                  placeholder='例如："把第 2 天博物馆换成夜生活" 或 "第 1 天加一顿特色美食"'
                  className="flex-1 bg-gray-800/60 border border-gray-600 text-white rounded-lg px-4 py-3 text-sm placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  disabled={isRefining}
                />
                <button
                  onClick={handleRefine}
                  disabled={isRefining || !refineMessage.trim()}
                  className="px-5 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-40 text-sm whitespace-nowrap"
                >
                  {isRefining ? "调整中..." : "应用修改"}
                </button>
              </div>
              {refineResult && (
                <div className={`mt-3 text-sm px-4 py-3 rounded-lg ${refineResult.startsWith("暂时无法") || refineResult.startsWith("请求失败") ? "bg-red-900/30 text-red-300" : "bg-purple-900/30 text-purple-200"}`}>
                  {refineResult}
                </div>
              )}
              {refineAlternatives && refineAlternatives.length > 0 && (
                <div className="mt-3">
                  <p className="text-gray-400 text-xs mb-2">Google Places 提供的其他备选：</p>
                  <div className="space-y-2">
                    {refineAlternatives.map((alt) => (
                      <div key={alt.place_id} className="flex items-center justify-between bg-gray-800/40 rounded-lg px-4 py-2.5">
                        <div>
                          <span className="text-white text-sm font-medium">{alt.name}</span>
                          <span className="text-gray-400 text-xs ml-2">{alt.address}</span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0 ml-4">
                          <span className="text-yellow-400 text-xs">⭐ {alt.rating}</span>
                          {alt.price_label && <span className="text-gray-400 text-xs">{alt.price_label}</span>}
                          <a
                            href={`https://www.google.com/maps/place/?q=place_id:${alt.place_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                          >
                            查看 →
                          </a>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex flex-wrap gap-2 mt-3">
                {["第 1 天安排更多美食", "最后一天增加夜生活", "移除最贵的活动", "把第 2 天换成户外活动"].map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setRefineMessage(suggestion)}
                    className="text-xs px-3 py-1.5 bg-gray-700/60 text-gray-300 rounded-full hover:bg-gray-600/60 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>

            {/* Daily Itinerary — Immersive Two-Panel Layout */}
            <div className="qt-day-panel glass-card rounded-2xl overflow-hidden flex" style={{ minHeight: "600px" }}>

              {/* Left Sidebar — Day List */}
              <div className="qt-day-sidebar w-52 shrink-0 border-r border-white/10 flex flex-col overflow-y-auto">
                <div className="px-4 py-3 border-b border-white/10">
                  <p className="text-xs font-semibold tracking-wider text-gray-500">你的旅程</p>
                  <p className="text-sm font-bold text-white mt-0.5">共 {itinerary.days.length} 天</p>
                  <p className="text-xs text-gray-400 mt-1">点选日期，查看当天安排</p>
                </div>
                <div className="qt-day-list flex-1">
                  {itinerary.days.map((day, dayIndex) => {
                    const isActive = activeDayIndex === dayIndex;
                    const dayLabel = formatChineseWeekday(day.date);
                    const dateLabel = formatChineseShortDate(day.date);
                    const categoryIcons: Record<string, string> = {
                      food: "🍽️", culture: "🏛️", nightlife: "🌙", nature: "🌿",
                      shopping: "🛍️", adventure: "⛰️", beaches: "🏖️",
                    };
                    const topCategories = [...new Set(day.blocks.map(b => b.activity.category))].slice(0, 3);

                    return (
                      <button
                        key={dayIndex}
                        onClick={() => setActiveDayIndex(dayIndex)}
                        className={`relative w-full text-left px-4 py-4 transition-all duration-200 border-b border-white/5 ${
                          isActive
                            ? "bg-purple-600/20 text-white"
                            : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
                        }`}
                      >
                        {isActive && (
                          <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-gradient-to-b from-purple-500 to-pink-500" />
                        )}
                        <div className="flex items-center justify-between mb-1">
                          <span className={`text-xs font-bold tracking-wider ${isActive ? "text-purple-400" : "text-gray-600"}`}>
                            第 {dayIndex + 1} 天
                          </span>
                          <span className={`text-xs ${isActive ? "text-purple-300" : "text-gray-600"}`}>
                            {day.blocks.length ? formatPriceWithRmb(day.total_cost, selectedCity?.default_currency) : "待估算"}
                          </span>
                        </div>
                        <div className="text-sm font-semibold mb-1">{dayLabel}，{dateLabel}</div>
                        <div className="flex gap-0.5 text-sm">
                          {topCategories.map(cat => (
                            <span key={cat} title={cat}>{categoryIcons[cat] ?? "📍"}</span>
                          ))}
                          <span className="text-xs text-gray-400 ml-1 self-center">{day.blocks.length ? `${day.blocks.length} 个地点` : "待补充安排"}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Right Panel — Active Day Content */}
              {(() => {
                const day = itinerary.days[activeDayIndex];
                if (!day) return null;
                const travelMode = formData.travel_mode || "mixed";
                const modeIcon: Record<string, string> = {
                  walking: "🚶", public_transport: "🚌", taxi: "🚕", self_drive: "🚗", mixed: "🗺️",
                };
                const modeLabel: Record<string, string> = {
                  walking: "步行", public_transport: "公共交通", taxi: "打车", self_drive: "自驾", mixed: "出行",
                };
                const gmapsTravelMode = travelMode === "public_transport" ? "transit"
                  : travelMode === "walking" ? "walking" : "driving";

                return (
                  <div className="flex-1 overflow-y-auto">
                    {/* Day header */}
                    <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-bold text-white">
                          第 {activeDayIndex + 1} 天 · {formatChineseDate(day.date)}
                        </h3>
                        <p className="text-sm text-gray-400 mt-0.5">
                          {day.blocks.length ? `${day.blocks.length} 个活动 · 预计 ${Math.round(day.total_duration_minutes / 60)} 小时` : "当前条件下未能排入景点"}
                        </p>
                      </div>
                      <span className="text-purple-300 font-semibold text-sm">
                        {day.blocks.length ? formatPriceWithRmb(day.total_cost, selectedCity?.default_currency) : "费用待估算"}
                      </span>
                    </div>

                    <div className="p-6">
                      {day.blocks.length > 0 && <div className="grid md:grid-cols-3 gap-3 mb-6">
                        <div className="rounded-xl bg-white/5 border border-white/10 px-4 py-3">
                          <p className="text-xs text-gray-400">今天怎么走</p>
                          <p className="text-sm font-semibold text-white mt-1">按时间顺序一个个去</p>
                        </div>
                        <div className="rounded-xl bg-white/5 border border-white/10 px-4 py-3">
                          <p className="text-xs text-gray-400">今天会玩多久</p>
                          <p className="text-sm font-semibold text-white mt-1">大约 {Math.round(day.total_duration_minutes / 60)} 小时</p>
                        </div>
                        <div className="rounded-xl bg-white/5 border border-white/10 px-4 py-3">
                          <p className="text-xs text-gray-400">今天预计花费</p>
                          <p className="text-sm font-semibold text-white mt-1">{formatPriceWithRmb(day.total_cost, selectedCity?.default_currency)}</p>
                          <p className="text-[11px] text-gray-400 mt-1">这是景点门票或基础消费估算，不含酒店、机票和大额购物。</p>
                        </div>
                      </div>}

                      {/* Map */}
                      {day.blocks.length > 0 ? <div className="qt-map-frame mb-6 rounded-xl overflow-hidden mx-auto" style={{ maxWidth: "75%" }}>
                        <GoogleItineraryMap
                          key={activeDayIndex}
                          activities={day.blocks.map(b => b.activity)}
                          routeSummary={day.route_summary}
                          currencyCode={selectedCity?.default_currency}
                        />
                      </div> : (
                        <div className="rounded-xl border border-amber-400/30 bg-white/5 p-8 text-gray-200">
                          <h4 className="text-lg font-semibold">这一天的行程待补充</h4>
                          <p className="mt-3 leading-relaxed">为避免重复游览，系统没有再次安排已经去过的景点。当前可用地点或预算、开放时间不足以覆盖这一天。</p>
                          <p className="mt-2 text-sm text-gray-400">你可以缩短旅行天数、提高预算或放宽筛选，也可以自行安排休息和自由活动。系统不会编造地点填满行程。</p>
                          <button type="button" onClick={() => setCurrentStep("preferences")} className="mt-5 px-4 py-2 rounded-lg bg-purple-600 text-white">调整条件并重新规划</button>
                        </div>
                      )}

                      {day.route_summary && (
                        <div className="mb-6 rounded-xl border border-cyan-500/30 p-4 text-gray-200">
                          <p className="font-semibold">从 {day.route_summary.lodging.name} 出发 · {formatTime(day.route_summary.departure_time)}</p>
                          <p className="text-sm mt-2">交通约 {day.route_summary.travel_minutes} 分钟 / {(day.route_summary.distance_meters / 1000).toFixed(1)} 公里 · 预计{day.route_summary.return_to_lodging ? "返回住宿" : "结束"} {formatTime(day.route_summary.finish_time)}</p>
                          <ol className="mt-3 space-y-3">{day.route_summary.legs.map((leg, i) => (
                            <li key={i} className="rounded-lg bg-white/5 p-3 text-sm">
                              <p>{leg.origin.name} → {leg.destination.name}</p>
                              <p className="text-cyan-300 mt-1">{modeLabel[leg.mode] || leg.mode} · 约 {leg.duration_minutes} 分钟 · {leg.source === "amap" ? (leg.cache_hit ? "高德缓存方案" : "高德方案") : "估算，未核验"}</p>
                              <details className="mt-1 text-gray-400"><summary className="cursor-pointer">查看交通说明</summary>{leg.instructions.map((text, j) => <p key={j}>{text}</p>)}</details>
                            </li>
                          ))}</ol>
                        </div>
                      )}

                      {/* Timeline */}
                      <div className="space-y-1">
                        {day.blocks.map((block, blockIndex) => {
                          const prevBlock = blockIndex > 0 ? day.blocks[blockIndex - 1] : null;
                          const localizedName = getLocalizedPlaceName(
                            block.activity.name,
                            block.activity.name_zh
                          );
                          const localizedDescription = getLocalizedDescription(
                            block.activity.description,
                            block.activity.description_zh
                          );
                          const routeReason = getLocalizedSelectionReason(
                            block.activity.explanation,
                            block.activity.category
                          );
                          const mapsUrl = prevBlock
                            ? `https://www.google.com/maps/dir/?api=1&origin=${prevBlock.activity.coordinates.latitude},${prevBlock.activity.coordinates.longitude}&destination=${block.activity.coordinates.latitude},${block.activity.coordinates.longitude}&travelmode=${gmapsTravelMode}`
                            : null;
                          const categoryColors: Record<string, string> = {
                            food: "bg-emerald-500", culture: "bg-purple-500", nightlife: "bg-pink-500",
                            nature: "bg-green-500", shopping: "bg-amber-500", adventure: "bg-red-500", beaches: "bg-cyan-500",
                          };
                          const dotColor = categoryColors[block.activity.category] ?? "bg-indigo-500";

                          return (
                            <div key={blockIndex}>
                              {/* Travel connector */}
                              {block.travel_time_from_previous && block.travel_time_from_previous > 0 && (
                                <div className="flex items-center gap-3 pl-[52px] py-1">
                                  <div className="w-px h-5 bg-purple-500/30" />
                                  <span className="text-xs text-gray-400 flex items-center gap-1.5">
                                    从上一个地点过来：{modeIcon[travelMode]} {block.travel_time_from_previous} 分钟{modeLabel[travelMode]}
                                    {mapsUrl && (
                                      <a href={mapsUrl} target="_blank" rel="noopener noreferrer"
                                        onClick={e => e.stopPropagation()}
                                        className="text-blue-400 hover:text-blue-300">
                                        · 打开导航 ↗
                                      </a>
                                    )}
                                  </span>
                                </div>
                              )}

                              {/* Activity card */}
                              <div
                                className="flex items-start gap-4 p-4 rounded-2xl border border-white/10 bg-white/[0.03] hover:bg-white/5 transition-colors cursor-pointer group"
                                onClick={() => setSelectedActivity(block.activity)}
                              >
                                {/* Timeline dot + time */}
                                <div className="flex flex-col items-center gap-1 shrink-0 w-12">
                                  <div className={`w-3 h-3 rounded-full ${dotColor} ring-2 ring-gray-900 mt-1`} />
                                  <span className="text-purple-400 font-mono text-xs">
                                    {formatTime(block.start_time)}
                                  </span>
                                </div>

                                {/* Content */}
                                <div className="flex-1 min-w-0">
                                  <div className="flex items-start justify-between gap-2">
                                    <div>
                                      <h4 className="font-semibold text-white group-hover:text-purple-200 transition-colors">
                                        {localizedName}
                                      </h4>
                                      <p className="text-xs text-gray-400 mt-1">
                                        这是一个{getCategoryLabel(block.activity.category)}地点
                                      </p>
                                    </div>
                                    <div className="text-right shrink-0">
                                      <p className="text-xs text-gray-400">基础花费估算</p>
                                      <span className="text-purple-300 font-medium text-sm">
                                        {formatPriceWithRmb(block.activity.cost, selectedCity?.default_currency)}
                                      </span>
                                      <p className="text-[11px] text-gray-500 mt-1">{block.activity.poi_source ? (block.activity.poi_source.cost_kind === "provider_average_spend" ? "高德人均消费参考，并非门票报价" : "按地点类别估算，实际费用待核实") : "通常指门票或基础消费"}</p>
                                    </div>
                                  </div>

                                  <div className="grid sm:grid-cols-3 gap-2 mt-3">
                                    <div className="rounded-lg bg-black/20 px-3 py-2">
                                      <p className="text-[11px] text-gray-400">建议停留</p>
                                      <p className="text-sm text-white font-medium">{block.activity.duration} 分钟</p>
                                    </div>
                                    <div className="rounded-lg bg-black/20 px-3 py-2">
                                      <p className="text-[11px] text-gray-400">用户评分</p>
                                      <p className="text-sm text-yellow-400 font-medium">{block.activity.poi_source?.rating_known === false ? "评分暂无数据" : `⭐ ${block.activity.rating.toFixed(1)}`}</p>
                                    </div>
                                    <div className="rounded-lg bg-black/20 px-3 py-2">
                                      <p className="text-[11px] text-gray-400">地点类型</p>
                                      <p className="text-sm text-white font-medium">{getCategoryLabel(block.activity.category)}</p>
                                    </div>
                                  </div>

                                  {localizedDescription && (
                                    <p className="text-gray-300 text-sm mt-3">
                                      <span className="text-gray-400">看点：</span>
                                      {localizedDescription}
                                    </p>
                                  )}

                                  {block.activity.poi_source?.provider === "amap" && (
                                    <p className="text-xs text-cyan-300 mt-3">来源：高德地点搜索
                                      {block.activity.poi_source.observed_at ? ` · ${new Date(block.activity.poi_source.observed_at).toLocaleString("zh-CN")} 获取` : ""}
                                    </p>
                                  )}

                                  <p className="text-gray-300 text-sm mt-3">
                                    <span className="text-gray-400">为什么这样安排：</span>
                                    {routeReason}
                                  </p>

                                  {blockIndex === 0 && (
                                    <p className="text-xs text-gray-400 mt-2">
                                      这站放在最前面，一般是因为它适合作为当天起点，或者与你的偏好更匹配。
                                    </p>
                                  )}

                                  <p className="text-xs text-blue-300 mt-3">点这张卡片，可以看更详细的信息</p>
                                </div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                );
              })()}
            </div>
          </div>
        )}

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
            currencyCode={selectedCity?.default_currency}
            onClose={() => setSelectedActivity(null)}
          />
        )}
      </div>
    </div>
  );
}
