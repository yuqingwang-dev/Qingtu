"use client";
import { useState } from "react";
import { cityLabel, CITY_HINTS } from "../lib/destinationLabels";

interface City {
  id: number; name: string; name_zh?: string | null; country: string; country_zh?: string | null;
  supports_real_routes?: boolean;
}
export default function DestinationPicker({ cities, selectedId, onSelect, onConfirm }: {
  cities: City[]; selectedId?: number; onSelect: (id: number) => void; onConfirm: (id: number) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = cities.filter(city => `${cityLabel(city)} ${city.name} ${city.country} ${city.country_zh || ""}`.toLowerCase().includes(query.trim().toLowerCase()));
  const selected = cities.find(city => city.id === selectedId);
  return <section className="qt-destinations" aria-label="选择目的地城市">
    <div className="qt-picker-heading"><div><p className="qt-eyebrow">旅程的第一站</p><h2>这次，想去哪里？</h2><p>选一座城市，剩下的我们一起安排。</p></div>
      <label className="qt-city-search"><span>搜索城市</span><input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="输入中文或英文城市名" /></label>
    </div>
    <div className="qt-city-grid">{filtered.map((city, index) => (
      <button type="button" key={city.id} className={`qt-city-card qt-city-tone-${index % 4}${selectedId === city.id ? " is-selected" : ""}`}
        aria-pressed={selectedId === city.id} onClick={() => onSelect(city.id)}>
        <span className="qt-city-art" aria-hidden="true"><span className="qt-city-sun" /><svg viewBox="0 0 160 66"><path d="M0 61h160M20 60V31h26v29m6 0V17h29v43m8 0V37h20v23m9 0V26h25v34" /><path d="M28 39h10m-10 8h10M61 26h10m-10 9h10m-10 9h10m-10 9h10m64-18h10m-10 9h10" /></svg></span>
        <span className="qt-city-card-content"><span className="qt-city-name">{cityLabel(city)}<span className="qt-selection-dot" aria-hidden="true">{selectedId === city.id ? "✓" : "+"}</span></span>
          <span className="qt-city-hint">{CITY_HINTS[city.name] || city.country_zh || city.country}</span>
          <span className="qt-city-capability">{city.supports_real_routes ? "支持真实交通路线" : "基础行程规划"}</span></span>
      </button>
    ))}</div>
    {!filtered.length && <p className="qt-empty" role="status">暂未找到这座城市。试试中文或英文名称，或切换“国内 / 国外”。</p>}
    <div className="qt-picker-bottom"><p>{selected ? <>已选择 <strong>{cityLabel(selected)}</strong>，下一步设置日期和喜好。</> : "点选一张城市卡片，就可以继续。"}</p>
      <button type="button" className="qt-button" disabled={!selected} onClick={() => selected && onConfirm(selected.id)}>下一步：安排怎么玩 <span aria-hidden="true">→</span></button>
    </div>
  </section>;
}
