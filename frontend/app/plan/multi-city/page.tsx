"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession, signIn } from "next-auth/react";
import dynamic from "next/dynamic";
import MultiCityResults from "../../components/MultiCityResults";
import Toast from "../../components/Toast";
import { getSessionId } from "../../lib/session";

// Dynamic import for map to avoid SSR issues
const WorldMapSelector = dynamic(() => import("@/components/WorldMapSelector"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-96 glass-card rounded-lg flex items-center justify-center">
      <p className="text-gray-300">世界地图加载中...</p>
    </div>
  ),
});

interface City {
  id: number;
  name: string;
  country: string;
  time_zone: string;
  default_currency: string;
}

interface ToastState {
  message: string;
  type: "error" | "success" | "info";
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const CATEGORIES = [
  "food",
  "culture",
  "nightlife",
  "nature",
  "shopping",
  "adventure",
  "beaches",
] as const;

const LOADING_STEPS = [
  { label: "正在规划路线", icon: "🗺️" },
  { label: "正在优化城市顺序", icon: "⚡" },
  { label: "正在安排活动", icon: "📅" },
  { label: "马上就好...", icon: "🎉" },
];

const CATEGORY_LABELS: Record<string, string> = {
  food: "美食 Food",
  culture: "文化 Culture",
  nightlife: "夜生活 Nightlife",
  nature: "自然 Nature",
  shopping: "购物 Shopping",
  adventure: "冒险 Adventure",
  beaches: "海滩 Beaches",
};

function LoadingProgress({ cityNames }: { cityNames?: string[] }) {
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setActiveStep((prev) => Math.min(prev + 1, LOADING_STEPS.length - 1));
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  const progress = ((activeStep + 1) / LOADING_STEPS.length) * 100;

  return (
    <div className="glass-card rounded-2xl p-10 flex flex-col items-center justify-center min-h-[340px]">
      <h2 className="text-2xl font-bold gradient-text mb-2">
        正在规划你的多城市旅程...
      </h2>
      {cityNames && cityNames.length > 0 && (
        <p className="text-purple-300 text-sm mb-1">{cityNames.join(" → ")}</p>
      )}
      <p className="text-gray-400 text-sm mb-8">通常需要 10 到 20 秒</p>

      {/* Progress bar */}
      <div className="w-full max-w-sm bg-gray-700 rounded-full h-2 mb-8 overflow-hidden">
        <div
          className="h-2 rounded-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all duration-700"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Steps */}
      <div className="w-full max-w-sm space-y-3">
        {LOADING_STEPS.map((step, i) => (
          <div key={i} className={`flex items-center gap-3 transition-opacity duration-500 ${i <= activeStep ? "opacity-100" : "opacity-30"}`}>
            <span className="text-xl w-8 text-center">
              {i < activeStep ? "✓" : i === activeStep ? step.icon : "○"}
            </span>
            <span className={`text-sm font-medium ${i < activeStep ? "text-green-400" : i === activeStep ? "text-white" : "text-gray-500"}`}>
              {step.label}
            </span>
            {i === activeStep && (
              <span className="ml-auto">
                <span className="inline-block w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function MultiCityPage() {
  const router = useRouter();
  const { data: session } = useSession();
  const [step, setStep] = useState<"select" | "plan">("select");
  const [cities, setCities] = useState<City[]>([]);
  const [selectedCities, setSelectedCities] = useState<number[]>([]);
  const [totalDays, setTotalDays] = useState(7);
  const [interests, setInterests] = useState<string[]>([]);
  const [pace, setPace] = useState<"relaxed" | "moderate" | "packed">("moderate");
  const [loading, setLoading] = useState(false);
  const [tripPlan, setTripPlan] = useState<any>(null);
  const [toast, setToast] = useState<ToastState | null>(null);
  const [daysAllocation, setDaysAllocation] = useState<any[]>([]);
  const [popularRoutes, setPopularRoutes] = useState<any[]>([]);

  useEffect(() => {
    fetchCities();
    fetchPopularRoutes();
  }, []);

  // Fetch days allocation when cities or total days change
  useEffect(() => {
    if (selectedCities.length >= 2) {
      fetchDaysAllocation();
    } else {
      setDaysAllocation([]);
    }
  }, [selectedCities, totalDays]);

  const fetchCities = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/cities`);
      if (response.ok) {
        const data = await response.json();
        setCities(data);
      }
    } catch (error) {
      console.error("Failed to fetch cities:", error);
    }
  };

  const fetchDaysAllocation = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/multi-city/suggest-days?city_ids=${selectedCities.join(",")}&total_days=${totalDays}`
      );
      if (response.ok) {
        const data = await response.json();
        setDaysAllocation(data.allocation || []);
      }
    } catch (error) {
      console.error("Failed to fetch days allocation:", error);
    }
  };

  const fetchPopularRoutes = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/multi-city/popular-routes`);
      if (response.ok) {
        const data = await response.json();
        setPopularRoutes(data.routes || []);
      }
    } catch (error) {
      console.error("Failed to fetch popular routes:", error);
    }
  };

  const toggleCity = (cityId: number) => {
    if (selectedCities.includes(cityId)) {
      setSelectedCities(selectedCities.filter((id) => id !== cityId));
    } else {
      if (selectedCities.length < 5) {
        setSelectedCities([...selectedCities, cityId]);
      }
    }
  };

  const toggleInterest = (category: string) => {
    if (interests.includes(category)) {
      setInterests(interests.filter((c) => c !== category));
    } else {
      setInterests([...interests, category]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (selectedCities.length < 2) {
      setToast({
        message: "请至少选择 2 座城市",
        type: "error",
      });
      return;
    }

    setLoading(true);
    setTripPlan(null);

    try {
      const authToken = (session as any)?.accessToken;
      const response = await fetch(`${API_BASE_URL}/api/v1/multi-city/plan`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-ID": getSessionId(),
          ...(authToken ? { "Authorization": `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          city_ids: selectedCities,
          total_days: totalDays,
          interests: interests.length > 0 ? interests : null,
          pace: pace,
        }),
      });

      if (!response.ok) {
        throw new Error("Failed to plan multi-city trip");
      }

      const data = await response.json();

      if (data.success && data.trip_plan) {
        setTripPlan(data.trip_plan);
        setToast({
          message: `已成功生成 ${data.trip_plan.total_cities} 城市行程！`,
          type: "success",
        });
        setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 100);
      } else {
        throw new Error("Invalid response from server");
      }
    } catch (error) {
      console.error("Error planning trip:", error);
      setToast({
        message: error instanceof Error ? error.message : "生成行程失败，请稍后重试。",
        type: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  const selectPopularRoute = (route: any) => {
    setSelectedCities(route.city_ids);
    setTotalDays(route.suggested_days);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const selectedCityObjects = cities.filter((city) =>
    selectedCities.includes(city.id)
  );

  if (tripPlan) {
    return (
      <div className="min-h-screen gradient-bg pt-24 pb-8 px-4">
        <div className="max-w-6xl mx-auto">
          <MultiCityResults tripPlan={tripPlan} onStartOver={() => setTripPlan(null)} />
        </div>
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    );
  }

  return (
    <div className="min-h-screen gradient-bg py-4 md:py-8 pt-20 px-2 md:px-4">
      <div className="max-w-7xl mx-auto">
        {/* Auth Prompt Banner */}
        {!session && (
          <div className="mb-6 glass-card rounded-lg p-4 border border-purple-500/30 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="text-2xl">💡</span>
              <div>
                <p className="text-white font-medium">登录后可保存并分享你的行程</p>
                <p className="text-gray-400 text-sm">创建账号后，可以在任何设备查看你的旅行计划</p>
              </div>
            </div>
            <button
              onClick={() => signIn("google")}
              className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg hover:opacity-90 transition-opacity whitespace-nowrap"
            >
              立即登录
            </button>
          </div>
        )}

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <button
            onClick={() => router.push("/")}
            className="px-4 py-2 glass-card rounded-lg hover:bg-purple-500/20 transition-colors text-white"
          >
            ← 返回首页
          </button>
          <h1 className="text-3xl md:text-4xl font-bold gradient-text">
            🗺️ 多城市规划
          </h1>
          <div className="w-24"></div> {/* Spacer for centering */}
        </div>

        {/* Progress Steps */}
        <div className="flex items-center justify-center mb-8 gap-4">
          <div className={`flex items-center gap-2 ${step === "select" ? "opacity-100" : "opacity-50"}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
              step === "select" ? "bg-gradient-to-r from-purple-500 to-pink-500" : "bg-gray-600"
            }`}>
              1
            </div>
            <span className="hidden md:inline text-white">选择城市</span>
          </div>
          <div className="w-12 h-0.5 bg-gray-600"></div>
          <div className={`flex items-center gap-2 ${step === "plan" ? "opacity-100" : "opacity-50"}`}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
              step === "plan" ? "bg-gradient-to-r from-purple-500 to-pink-500" : "bg-gray-600"
            }`}>
              2
            </div>
            <span className="hidden md:inline text-white">规划行程</span>
          </div>
        </div>

        {/* Step 1: City Selection with Map */}
        {step === "select" && (
          <div className="space-y-6">
            <div className="h-[680px]">
              <WorldMapSelector
                cities={cities}
                selectedCities={selectedCities}
                onCitySelect={toggleCity}
                multiSelect={true}
                title={`选择你的目的地 (${selectedCities.length}/5)`}
              />
            </div>

            {/* Selected Cities Summary */}
            {selectedCities.length > 0 && (
              <div className="glass-card rounded-2xl p-6">
                <h3 className="text-xl font-bold text-white mb-4">
                  已选城市 ({selectedCities.length})
                </h3>
                <div className="flex flex-wrap gap-2 mb-4">
                  {selectedCityObjects.map((city) => (
                    <div
                      key={city.id}
                      className="px-4 py-2 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg text-white flex items-center gap-2"
                    >
                      {city.name}, {city.country}
                      <button
                        onClick={() => toggleCity(city.id)}
                        className="ml-2 hover:text-red-300"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
                <button
                  onClick={() => setStep("plan")}
                  disabled={selectedCities.length < 2}
                  className="w-full py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {selectedCities.length < 2
                    ? "至少选择 2 座城市后继续"
                    : `使用这 ${selectedCities.length} 座城市继续`}
                </button>
              </div>
            )}

            {/* Popular Routes */}
            {popularRoutes.length > 0 && selectedCities.length === 0 && (
              <div className="glass-card rounded-2xl p-6">
                <h3 className="text-xl font-bold text-white mb-4">
                  ✨ 热门路线
                </h3>
                <div className="grid md:grid-cols-2 gap-4">
                  {popularRoutes.map((route, index) => (
                    <button
                      key={index}
                      onClick={() => selectPopularRoute(route)}
                      className="p-4 bg-gray-800/30 rounded-lg hover:bg-gray-800/50 transition-colors text-left"
                    >
                      <div className="font-medium text-white mb-2">
                        {route.name}
                      </div>
                      <div className="text-sm text-gray-400">
                        {route.cities.join(" → ")}
                      </div>
                      <div className="text-xs text-purple-300 mt-2">
                        建议 {route.suggested_days} 天
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <LoadingProgress cityNames={cities.filter(c => selectedCities.includes(c.id)).map(c => c.name)} />
        )}

        {/* Step 2: Planning Form */}
        {step === "plan" && !loading && (
          <div className="glass-card rounded-2xl p-6">
            <div className="mb-6">
              <button
                onClick={() => setStep("select")}
                className="text-purple-400 hover:text-purple-300 text-sm mb-4"
              >
                ← 重新选择城市
              </button>
              <h2 className="text-2xl font-bold gradient-text mb-2">
                规划你的多城市旅程
              </h2>
              <div className="flex flex-wrap gap-2">
                {selectedCityObjects.map((city, index) => (
                  <span key={city.id} className="text-gray-300">
                    {city.name}
                    {index < selectedCityObjects.length - 1 && " → "}
                  </span>
                ))}
              </div>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Total Days */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  总旅行天数
                </label>
                <input
                  type="number"
                  min={selectedCities.length}
                  max={30}
                  value={totalDays}
                  onChange={(e) => setTotalDays(Number(e.target.value))}
                  className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                  required
                />
                <p className="text-sm text-gray-400 mt-1">
                  最少 {selectedCities.length} 天（每座城市至少 1 天）
                </p>
              </div>

              {/* Days Allocation Preview */}
              {daysAllocation.length > 0 && (
                <div className="p-4 bg-gray-800/30 rounded-lg">
                  <h3 className="font-medium text-white mb-2">
                    建议停留天数：
                  </h3>
                  <div className="space-y-1">
                    {daysAllocation.map((allocation: any, index: number) => (
                      <div key={index} className="text-sm text-gray-300">
                        {allocation.city_name}：{allocation.days} {allocation.days === 1 ? '天' : '天'}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Interests */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-3">
                  兴趣偏好（可选）
                </label>
                <div className="flex flex-wrap gap-2">
                  {CATEGORIES.map((category) => (
                    <button
                      key={category}
                      type="button"
                      onClick={() => toggleInterest(category)}
                      className={`px-4 py-2 rounded-lg transition-all ${
                        interests.includes(category)
                          ? "bg-gradient-to-r from-purple-500 to-pink-500 text-white"
                          : "bg-gray-800/50 text-gray-300 hover:bg-gray-700/50"
                      }`}
                    >
                      {CATEGORY_LABELS[category] || category}
                    </button>
                  ))}
                </div>
              </div>

              {/* Pace */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  旅行节奏
                </label>
                <select
                  value={pace}
                  onChange={(e) => setPace(e.target.value as any)}
                  className="w-full px-4 py-2 bg-gray-800/50 border border-purple-500/30 rounded-lg text-white focus:outline-none focus:border-purple-500"
                >
                  <option value="relaxed">轻松 Relaxed - 慢一点更从容</option>
                  <option value="moderate">均衡 Moderate - 节奏平衡</option>
                  <option value="packed">紧凑 Packed - 尽量多玩</option>
                </select>
              </div>

              {/* Submit Button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {loading ? "正在生成行程..." : "生成多城市行程"}
              </button>
            </form>
          </div>
        )}

        {/* Toast */}
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    </div>
  );
}
