"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import TravelKnowledge from "../components/TravelKnowledge";

export default function KnowledgePage() {
  const [cityId, setCityId] = useState<number | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/v1/cities`, { signal: controller.signal })
      .then(res => { if (!res.ok) throw new Error("城市目录加载失败，请检查后端服务。"); return res.json(); })
      .then((cities: { id: number; name: string; name_zh?: string }[]) => {
        const city = cities.find(c => c.name_zh === "成都" || c.name.toLowerCase() === "chengdu");
        if (!city) throw new Error("请先导入成都城市数据。");
        setCityId(city.id);
      })
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "加载失败。"); });
    return () => controller.abort();
  }, []);
  return <div className="gradient-bg min-h-screen py-10"><div className="qt-container max-w-4xl space-y-5">
    <Link href="/" className="underline">← 返回晴途首页</Link>
    <h1 className="text-3xl font-bold">成都出游 · 有来源的攻略</h1>
    <p>无需先生成行程，即可查阅官方参观资料。首批覆盖三个景点，其他城市逐步补充。</p>
    {error ? <p role="alert">{error}</p> : cityId ? <TravelKnowledge cityId={cityId} cityName="成都" /> : <p role="status">正在加载城市…</p>}
  </div></div>;
}
