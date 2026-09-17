"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
type Source = { title: string; url: string; city: string; poi_name: string; reviewed_on: string; expires_on: string };
type Citation = Source & { id: string; topic: string; excerpt: string; source_version: number };
type Answer = { status: string; message: string; citations: Citation[]; warnings: string[]; retrieval_mode: string; answer_mode: string; source_links?: { title: string; url: string }[] };
const prompts = ["需要预约或带身份证吗？", "行李在哪里寄存？", "带老人和小孩有什么注意事项？", "拍照可以开闪光灯吗？"];

export default function TravelKnowledge({ cityId, cityName, places = [], travelDate }: {
  cityId: number; cityName: string; places?: string[]; travelDate?: string;
}) {
  const [sources, setSources] = useState<Source[]>([]);
  const [poi, setPoi] = useState("");
  const [question, setQuestion] = useState(prompts[0]);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [error, setError] = useState("");
  const [useAI, setUseAI] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  const options = useMemo(() => [...new Set(sources.filter(s => s.city === cityName).map(s => s.poi_name))], [sources, cityName]);
  const placesKey = [...new Set(places)].join("|");

  useEffect(() => {
    const controller = new AbortController();
    setCatalogLoading(true);
    setSources([]);
    setPoi("");
    setAnswer(null);
    setError("");
    fetch(`${API}/api/v1/knowledge/status`, { signal: controller.signal })
      .then(res => { if (!res.ok) throw new Error("知识库未就绪，请确认后端已完成迁移和资料导入。"); return res.json(); })
      .then(data => {
        const all: Source[] = data.sources;
        setSources(all);
        const local = all.filter(s => s.city === cityName);
        const matching = local.find(s => placesKey.includes(s.poi_name) || (s.poi_name.includes("熊猫") && placesKey.includes("熊猫")));
        setPoi((placesKey ? matching : local[0])?.poi_name || "");
      })
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "资料加载失败，请重试。"); })
      .finally(() => { if (!controller.signal.aborted) setCatalogLoading(false); });
    return () => { controller.abort(); activeRequest.current?.abort(); };
  }, [cityId, cityName, placesKey]);

  const ask = useCallback(async (text: string, ai: boolean) => {
    if (!poi || text.trim().length < 2) return;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 45000);
    setLoading(true); setError(""); setAnswer(null);
    try {
      const res = await fetch(`${API}/api/v1/knowledge/ask`, {
        method: "POST", headers: { "Content-Type": "application/json" }, signal: controller.signal,
        body: JSON.stringify({ city_id: cityId, poi_name: poi, question: text.trim(), travel_date: travelDate || null, use_ai: ai }),
      });
      if (!res.ok) throw new Error(res.status === 429 ? "查询繁忙，请稍后再试。" : "攻略查询失败，请检查后端服务后重试。");
      const data: Answer = await res.json();
      if (activeRequest.current === controller) setAnswer(data);
    } catch (err) {
      if (activeRequest.current === controller) setError(controller.signal.aborted ? "查询已取消或超时，请重试。" : err instanceof Error ? err.message : "查询失败。");
    } finally {
      clearTimeout(timeout);
      if (activeRequest.current === controller) setLoading(false);
    }
  }, [cityId, poi, travelDate]);

  // Initial tips are local-only. Changing scope cancels the previous request.
  useEffect(() => {
    setAnswer(null); setError(""); setLoading(false);
    if (poi) void ask(prompts[0], false);
    return () => { activeRequest.current?.abort(); activeRequest.current = null; };
  }, [poi, ask]);

  function submit(event: FormEvent) { event.preventDefault(); void ask(question, useAI); }

  return (
    <section className="glass-card rounded-2xl p-6" aria-labelledby="travel-knowledge-heading">
      <p className="qt-eyebrow">有据可查 · 旅行知识库</p>
      <h3 id="travel-knowledge-heading" className="text-xl font-bold mb-2">出发前，先把小事弄明白</h3>
      <p className="text-sm text-gray-600 mb-4">查预约、行李和入园须知。每条摘要附官方原文；不是实时余票或天气查询，也不改变你的行程。</p>
      {catalogLoading && <p role="status">正在检查资料覆盖范围…</p>}
      {!catalogLoading && !error && options.length === 0 && <p>暂未收录{cityName}的核验攻略，行程规划仍可正常使用。不会套用其他城市的资料。</p>}
      {options.length > 0 && <>
        <p className="text-sm mb-3">目前覆盖：{options.join("、")}。不在列表中的地点暂未收录，不代表无法游玩。</p>
        {!poi && placesKey && <p className="text-sm mb-3">这份行程暂未匹配到已收录景点。你也可以在下方手动选择，查阅成都其他景点资料。</p>}
        <label className="block text-sm font-semibold mb-4">想了解哪个景点？
          <select className="block w-full mt-2 rounded-lg border px-3 py-2" value={poi} onChange={e => { setPoi(e.target.value); setQuestion(prompts[0]); }}>
            <option value="" disabled>请选择景点</option>
            {options.map(name => <option key={name} value={name}>{name}</option>)}
          </select>
        </label>
        <div className="flex flex-wrap gap-2 mb-4" aria-label="常见问题">
          {prompts.map(text => <button type="button" key={text} disabled={!poi || loading} className="rounded-full border border-green-700 px-3 py-2 text-sm" onClick={() => { setQuestion(text); void ask(text, useAI); }}>{text}</button>)}
        </div>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm font-semibold" htmlFor="knowledge-question">再问一个问题</label>
          <input id="knowledge-question" className="border rounded-lg w-full px-3 py-2" value={question} onChange={e => setQuestion(e.target.value)} maxLength={500} minLength={2} required placeholder="例如：武侯祠可以寄存行李吗？" />
          <div className="flex flex-wrap gap-4 items-center justify-between">
            <label className="flex gap-2 items-center text-sm"><input type="checkbox" checked={useAI} onChange={e => setUseAI(e.target.checked)} />让 AI 帮我筛选资料（可选，会调用已配置的模型）</label>
            <button type="submit" disabled={!poi || loading} className="qt-button qt-button-primary">{loading ? "正在查找资料…" : "查找有来源的回答"}</button>
          </div>
        </form>
      </>}
      <div className="mt-4 space-y-3" aria-live="polite" aria-busy={loading}>
        {error && <p role="alert" className="text-red-700">{error}</p>}
        {answer && <>
          <p className="text-sm">{answer.message}</p>
          {answer.source_links?.map(s => <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer" className="block underline text-sm">查看最新公告：{s.title} ↗</a>)}
          {answer.citations.map((c, index) => <article key={c.id} className="rounded-xl border border-green-700/20 p-4 bg-green-50/60">
            <h4 className="font-semibold mb-2">{index + 1}. {c.poi_name} · {c.topic}</h4>
            <p className="leading-relaxed">{c.excerpt}</p>
            <a href={c.url} target="_blank" rel="noopener noreferrer" className="inline-block mt-3 underline text-sm">查看官方原文：{c.title} ↗</a>
            <p className="text-xs text-gray-600 mt-2">人工核对：{c.reviewed_on} · 建议复核前使用至：{c.expires_on} · 摘要版本 {c.source_version}</p>
          </article>)}
          {answer.warnings.map(w => <p className="text-sm text-amber-800" key={w}>{w}</p>)}
          {answer.citations.length > 0 && <details className="text-xs text-gray-600"><summary className="cursor-pointer">这次回答是怎么来的？</summary>
            <p className="mt-2">{answer.retrieval_mode === "hybrid_bm25_vector_rrf" ? "中文本地向量 + BM25 关键词检索，RRF 合并排序。" : "关键词检索。"}{answer.answer_mode === "ai_selected_evidence" ? " AI 从已检索资料中选择引用；展示内容仍为核对摘要。" : " 展示核对摘要，没有使用 AI 编造回答。"}</p>
          </details>}
        </>}
      </div>
    </section>
  );
}
