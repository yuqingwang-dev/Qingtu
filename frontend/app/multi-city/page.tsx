"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import MultiCityResults from "../components/MultiCityResults";
import Toast from "../components/Toast";

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

export default function MultiCityPage() {
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
        message: "Please select at least 2 cities",
        type: "error",
      });
      return;
    }

    setLoading(true);
    setTripPlan(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/multi-city/plan`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
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
          message: `Successfully planned your ${data.trip_plan.total_cities}-city trip!`,
          type: "success",
        });
        setTimeout(() => window.scrollTo({ top: 0, behavior: "smooth" }), 100);
      } else {
        throw new Error("Invalid response from server");
      }
    } catch (error) {
      console.error("Error planning trip:", error);
      setToast({
        message: error instanceof Error ? error.message : "Failed to plan trip. Please try again.",
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
      <div className="min-h-screen gradient-bg py-8 px-4">
        <div className="max-w-6xl mx-auto">
          <MultiCityResults tripPlan={tripPlan} onStartOver={() => setTripPlan(null)} />
        </div>
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    );
  }

  return (
    <div className="min-h-screen gradient-bg py-4 md:py-8 px-2 md:px-4">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="text-center mb-6 md:mb-8 animate-fade-in">
          <div className="inline-block mb-4">
            <Link
              href="/"
              className="glass px-6 py-3 rounded-full font-semibold text-gray-700 hover:bg-white/40 transition-all flex items-center gap-2 hover-lift shadow-lg"
            >
              ← Back to Single City
            </Link>
          </div>
          <div className="inline-block mb-4">
            <div className="text-6xl md:text-7xl mb-4 animate-float">🗺️</div>
          </div>
          <h1 className="text-4xl md:text-6xl font-bold gradient-text mb-3">
            Multi-City Planner
          </h1>
          <p className="text-lg md:text-2xl text-white font-semibold drop-shadow-lg">
            Plan Your Perfect Multi-Destination Adventure
          </p>
        </div>

        {/* Main Form */}
        <form onSubmit={handleSubmit} className="glass-strong rounded-3xl shadow-2xl p-4 md:p-8 animate-scale-in border border-white/30 mb-8">
          <div className="space-y-8">
            {/* City Selection */}
            <div>
              <div className="flex items-center gap-3 mb-4">
                <span className="text-3xl">🌍</span>
                <h2 className="text-2xl md:text-3xl font-bold gradient-text">
                  Select Cities ({selectedCities.length}/5)
                </h2>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                {cities.map((city) => {
                  const isSelected = selectedCities.includes(city.id);
                  return (
                    <button
                      key={city.id}
                      type="button"
                      onClick={() => toggleCity(city.id)}
                      disabled={!isSelected && selectedCities.length >= 5}
                      className={`p-3 rounded-xl border-2 transition-all font-medium ${
                        isSelected
                          ? "border-primary-500 bg-primary-50 text-primary-700 shadow-md"
                          : selectedCities.length >= 5
                          ? "border-gray-200 bg-gray-50 text-gray-400 cursor-not-allowed"
                          : "border-white/30 glass hover:border-primary-300 hover:bg-primary-50 hover-lift"
                      }`}
                    >
                      <div className="font-semibold text-sm">{city.name}</div>
                      <div className="text-xs opacity-75">{city.country}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Selected Cities Preview */}
            {selectedCities.length >= 2 && daysAllocation.length > 0 && (
              <div className="p-4 glass rounded-2xl border border-green-200 animate-slide-up">
                <h3 className="text-sm font-semibold text-green-800 mb-3 flex items-center gap-2">
                  <span>✨</span>
                  <span>Your Trip Route</span>
                </h3>
                <div className="space-y-2">
                  {daysAllocation.map((allocation, index) => (
                    <div key={allocation.city_id} className="flex items-center gap-2">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-accent-500 text-white flex items-center justify-center text-sm font-bold shadow-md">
                        {index + 1}
                      </div>
                      <div className="flex-1 font-medium text-gray-800">
                        {allocation.city_name}
                      </div>
                      <div className="text-sm text-gray-700 font-semibold">
                        {allocation.suggested_days} {allocation.suggested_days === 1 ? "day" : "days"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Trip Duration */}
            {selectedCities.length >= 2 && (
              <>
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <span className="text-3xl">📅</span>
                    <h2 className="text-2xl md:text-3xl font-bold gradient-text">
                      Trip Duration: {totalDays} days
                    </h2>
                  </div>
                  <input
                    type="range"
                    min="4"
                    max="30"
                    value={totalDays}
                    onChange={(e) => setTotalDays(parseInt(e.target.value))}
                    className="w-full h-3 glass rounded-full appearance-none cursor-pointer accent-primary-500"
                  />
                  <div className="flex justify-between text-xs text-gray-600 mt-2 font-medium">
                    <span>4 days</span>
                    <span>30 days</span>
                  </div>
                </div>

                {/* Interests */}
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <span className="text-3xl">❤️</span>
                    <h2 className="text-2xl md:text-3xl font-bold gradient-text">
                      Interests (Optional)
                    </h2>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {CATEGORIES.map((category) => {
                      const isSelected = interests.includes(category);
                      return (
                        <button
                          key={category}
                          type="button"
                          onClick={() => toggleInterest(category)}
                          className={`px-4 py-3 rounded-xl border-2 text-sm capitalize transition-all font-semibold ${
                            isSelected
                              ? "border-primary-500 bg-gradient-to-br from-primary-500 to-accent-500 text-white shadow-glow"
                              : "border-white/30 glass hover:border-primary-400 hover:bg-primary-50 hover-lift"
                          }`}
                        >
                          {category}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Pace */}
                <div>
                  <div className="flex items-center gap-3 mb-4">
                    <span className="text-3xl">⚡</span>
                    <h2 className="text-2xl md:text-3xl font-bold gradient-text">
                      Trip Pace
                    </h2>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {(["relaxed", "moderate", "packed"] as const).map((p) => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => setPace(p)}
                        className={`px-6 py-4 rounded-xl border-2 text-sm capitalize transition-all ${
                          pace === p
                            ? "border-primary-500 bg-gradient-to-br from-primary-50 to-accent-50 text-primary-700 font-bold shadow-md"
                            : "border-white/30 glass hover:border-primary-300 hover-lift"
                        }`}
                      >
                        <div className="font-bold text-base">{p}</div>
                        <div className="text-xs opacity-75 mt-1">
                          {p === "relaxed" && "2-3 activities/day"}
                          {p === "moderate" && "4-5 activities/day"}
                          {p === "packed" && "6+ activities/day"}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Submit Button */}
                <button
                  type="submit"
                  disabled={loading || selectedCities.length < 2}
                  className={`w-full py-4 px-6 rounded-full font-bold text-lg transition-all shadow-xl ${
                    loading || selectedCities.length < 2
                      ? "bg-gray-400 cursor-not-allowed text-white"
                      : "bg-gradient-to-r from-primary-600 to-accent-600 hover:shadow-glow text-white hover-lift"
                  }`}
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg
                        className="animate-spin h-6 w-6"
                        xmlns="http://www.w3.org/2000/svg"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        ></circle>
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                        ></path>
                      </svg>
                      Planning your {selectedCities.length}-city adventure...
                    </span>
                  ) : (
                    `🚀 Plan ${selectedCities.length}-City Trip`
                  )}
                </button>
              </>
            )}

            {/* Help text */}
            {selectedCities.length === 1 && (
              <p className="text-center text-gray-600 font-medium">
                Select at least one more city to start planning your multi-city adventure ✈️
              </p>
            )}
            {selectedCities.length === 0 && (
              <p className="text-center text-gray-600 font-medium">
                Select 2-5 cities above to begin planning your trip 🌎
              </p>
            )}
          </div>
        </form>

        {/* Popular Routes */}
        {popularRoutes.length > 0 && !tripPlan && (
          <div className="glass-strong rounded-3xl shadow-2xl p-6 md:p-8 animate-fade-in border border-white/30">
            <h2 className="text-2xl md:text-3xl font-bold gradient-text mb-2 flex items-center gap-3">
              <span>🌟</span>
              <span>Popular Routes</span>
            </h2>
            <p className="text-gray-600 mb-6 font-medium">
              Get inspired by these curated multi-city itineraries
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {popularRoutes.map((route, index) => (
                <div
                  key={index}
                  className="glass border-2 border-white/30 rounded-2xl p-5 hover:shadow-xl transition-all hover-lift"
                >
                  <h3 className="text-lg font-bold text-gray-800 mb-2">
                    {route.name}
                  </h3>
                  <p className="text-sm text-gray-600 mb-4">{route.description}</p>

                  <div className="mb-4">
                    <div className="text-xs font-bold text-gray-500 mb-2">
                      CITIES:
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {route.cities.map((city: string, i: number) => (
                        <span
                          key={i}
                          className="px-3 py-1 bg-gradient-to-r from-primary-100 to-accent-100 text-primary-700 rounded-full text-xs font-semibold"
                        >
                          {city}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold text-gray-700">
                      {route.suggested_days} days
                    </div>
                    <button
                      type="button"
                      onClick={() => selectPopularRoute(route)}
                      className="px-4 py-2 bg-gradient-to-r from-primary-600 to-accent-600 text-white rounded-full text-sm font-bold hover:shadow-glow transition-all"
                    >
                      Select Route
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  );
}
