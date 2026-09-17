"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession, signIn } from "next-auth/react";
import { api, type ItineraryListItem } from "../lib/api";
import Toast from "../components/Toast";

interface ToastState {
  message: string;
  type: "error" | "success" | "info";
}

export default function SavedItinerariesPage() {
  const router = useRouter();
  const { data: session, status } = useSession();
  const [itineraries, setItineraries] = useState<ItineraryListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<ToastState | null>(null);

  useEffect(() => {
    if (status !== "loading") {
      loadItineraries();
    }
  }, [status]);

  const loadItineraries = async () => {
    setLoading(true);
    try {
      const authToken = (session as any)?.accessToken;
      const data = await api.listItineraries(authToken);
      setItineraries(data);
    } catch (error) {
      console.error("Error loading itineraries:", error);
      setToast({
        message: "行程加载失败，请稍后重试。",
        type: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确定删除这份行程吗？此操作无法撤销。")) return;

    try {
      const authToken = (session as any)?.accessToken;
      await api.deleteItinerary(id, authToken);
      setToast({ message: "行程已删除。", type: "success" });
      // Refresh list
      loadItineraries();
    } catch (error) {
      console.error("Error deleting itinerary:", error);
      setToast({
        message: "删除失败，请稍后重试。",
        type: "error",
      });
    }
  };

  const handleShare = async (id: string) => {
    try {
      const authToken = (session as any)?.accessToken;
      const result = await api.shareItinerary(id, authToken);
      const shareUrl = `${window.location.origin}/share/${result.share_token}`;

      // Copy to clipboard
      await navigator.clipboard.writeText(shareUrl);

      setToast({
        message: "分享链接已复制，可以发给同行的人。",
        type: "success",
      });
    } catch (error) {
      console.error("Error sharing itinerary:", error);
      setToast({
        message: "分享链接生成失败，请稍后重试。",
        type: "error",
      });
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString("zh-CN", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen gradient-bg flex items-center justify-center p-4">
        <div className="text-center glass-strong p-12 rounded-3xl shadow-2xl animate-scale-in">
          <div className="relative w-20 h-20 mx-auto mb-6">
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-primary-500 border-r-accent-500 animate-spin"></div>
            <div className="absolute inset-2 rounded-full border-4 border-transparent border-b-accent-500 border-l-primary-500 animate-spin" style={{animationDirection: "reverse", animationDuration: "1s"}}></div>
          </div>
          <h2 className="text-2xl font-bold gradient-text mb-2">
            正在翻开你的出游手账…
          </h2>
        </div>
      </div>
    );
  }

  return (
    <>
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
      <div className="min-h-screen gradient-bg py-8 px-4 pt-20">
        <div className="max-w-6xl mx-auto">
          {/* Auth Prompt for non-authenticated users */}
          {!session && status !== "loading" && (
            <div className="mb-6 glass-card rounded-lg p-6 border border-purple-500/30 text-center">
              <div className="text-4xl mb-3">🔒</div>
              <h2 className="text-2xl font-bold text-white mb-2">把喜欢的旅程，收进晴途</h2>
              <p className="text-gray-400 mb-4">登录后即可保存、查看和分享行程。暂时不登录也能先去规划。</p>
              <button
                onClick={() => signIn("google")}
                className="px-6 py-3 bg-gradient-to-r from-purple-500 to-pink-500 text-white rounded-lg hover:opacity-90 transition-opacity font-medium"
              >
                使用 Google 登录
              </button>
            </div>
          )}
          {/* Header */}
          <div className="mb-8 animate-slide-up">
            <div className="glass-strong p-6 rounded-3xl shadow-2xl">
              <div className="flex items-center justify-between mb-4">
                <button
                  onClick={() => router.push("/")}
                  className="glass px-6 py-3 rounded-full font-semibold text-gray-700 hover:bg-white/40 transition-all flex items-center gap-2 hover-lift shadow-lg"
                >
                  ← 返回首页
                </button>
              </div>
              <h1 className="text-4xl md:text-5xl font-bold gradient-text mb-2">
                我的出游手账
              </h1>
              <p className="text-gray-700 font-medium text-lg">
                {itineraries.length} 份已保存的行程
              </p>
            </div>
          </div>

          {/* Itineraries List */}
          {itineraries.length === 0 ? (
            <div className="glass-strong rounded-3xl shadow-2xl p-12 text-center animate-scale-in">
              <div className="text-6xl mb-4">🗺️</div>
              <h2 className="text-2xl font-bold text-gray-800 mb-2">
                还没有收藏的旅程
              </h2>
              <p className="text-gray-600 mb-6">
                先规划一次小小的出发，再把喜欢的安排保存下来。
              </p>
              <button
                onClick={() => router.push("/")}
                className="bg-gradient-to-r from-primary-500 to-accent-500 text-white px-8 py-3 rounded-full font-semibold hover:shadow-glow transition-all hover-lift shadow-xl"
              >
                规划一段新旅程
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {itineraries.map((itinerary, idx) => (
                <div
                  key={itinerary.id}
                  className="glass-strong rounded-2xl shadow-xl p-6 hover-lift animate-slide-up border border-white/30"
                  style={{ animationDelay: `${idx * 100}ms` }}
                >
                  {/* City Names */}
                  <div className="mb-4">
                    <h3 className="text-xl font-bold gradient-text mb-2">
                      {itinerary.city_names.join(", ")}
                    </h3>
                    <p className="text-sm text-gray-600 font-medium">
                      {formatDate(itinerary.start_date)} - {formatDate(itinerary.end_date)}
                    </p>
                  </div>

                  {/* Summary Stats */}
                  <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="glass rounded-xl p-3 text-center">
                      <div className="text-2xl mb-1">💵</div>
                      <p className="text-xs text-gray-600 mb-1">费用参考（原币）</p>
                      <p className="text-lg font-bold bg-gradient-to-r from-primary-600 to-accent-600 bg-clip-text text-transparent">
                        {itinerary.total_cost.toFixed(0)}
                      </p>
                    </div>
                    <div className="glass rounded-xl p-3 text-center">
                      <div className="text-2xl mb-1">📅</div>
                      <p className="text-xs text-gray-600 mb-1">旅行天数</p>
                      <p className="text-lg font-bold bg-gradient-to-r from-primary-600 to-accent-600 bg-clip-text text-transparent">
                        {itinerary.days_count}
                      </p>
                    </div>
                  </div>

                  {/* Status Badges */}
                  <div className="flex gap-2 mb-4">
                    {itinerary.is_public && (
                      <span className="px-3 py-1 bg-green-100 text-green-700 rounded-full text-xs font-semibold">
                        已公开分享
                      </span>
                    )}
                    {itinerary.view_count > 0 && (
                      <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-semibold">
                        👁️ {itinerary.view_count} 次浏览
                      </span>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => router.push(`/itinerary/${itinerary.id}`)}
                      className="w-full bg-gradient-to-r from-primary-500 to-accent-500 text-white px-4 py-2 rounded-full font-semibold hover:shadow-glow transition-all text-sm"
                    >
                      查看行程
                    </button>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleShare(itinerary.id)}
                        className="flex-1 glass px-4 py-2 rounded-full font-semibold text-gray-700 hover:bg-white/40 transition-all text-sm"
                      >
                        🔗 分享
                      </button>
                      <button
                        onClick={() => handleDelete(itinerary.id)}
                        className="flex-1 bg-red-100 text-red-600 px-4 py-2 rounded-full font-semibold hover:bg-red-200 transition-all text-sm"
                      >
                        🗑️ 删除
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
