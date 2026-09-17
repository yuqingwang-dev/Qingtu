"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";

const destinations = [
  { name: "成都", code: "Chengdu", hint: "慢一点，尝尝生活的滋味", symbol: "茶", tone: "mint" },
  { name: "杭州", code: "Hangzhou", hint: "沿着湖畔，把心情放晴", symbol: "湖", tone: "blue" },
  { name: "北京", code: "Beijing", hint: "走进街巷，遇见新故事", symbol: "城", tone: "peach" },
  { name: "上海", code: "Shanghai", hint: "在城市转角，发现惊喜", symbol: "光", tone: "sand" },
];

export default function LandingPage() {
  const router = useRouter();
  const [city, setCity] = useState("Chengdu");
  return <div className="qt-home">
    <section className="qt-hero qt-container">
      <div className="qt-hero-copy">
        <p className="qt-eyebrow"><span className="qt-status-dot" /> 晴途 · 你的轻松出游搭子</p>
        <h1>把好心情，<br /><span>安排进旅程。</span></h1>
        <p className="qt-hero-description">想去哪、喜欢什么、想玩多久？<br />把这些告诉晴途，一起排出舒服的出游节奏。</p>
        <form className="qt-quick-plan" onSubmit={event => { event.preventDefault(); router.push(`/plan/single-city${city ? "?city=" + city : ""}`); }}>
          <label htmlFor="home-destination"><span>这次想去</span><select id="home-destination" value={city} onChange={event => setCity(event.target.value)}>
            {destinations.map(item => <option key={item.code} value={item.code}>{item.name}</option>)}<option value="">看看更多城市</option>
          </select></label>
          <button className="qt-button" type="submit">开始规划 <span aria-hidden="true">↗</span></button>
        </form>
        <Link href="/knowledge" className="inline-block mt-3 underline text-sm">先查攻略：预约、行李和入园须知 →</Link>
        <p className="qt-small-note">不用先登录，也能生成行程。保存与分享时再登录。</p>
        <div className="qt-hero-promises"><span>✓ 中文清楚好读</span><span>✓ 地点来源可查</span><span>✓ 节奏由你决定</span></div>
      </div>
      <div className="qt-hero-art" aria-label="轻松出游的路线插画与行程示意">
        <div className="qt-art-caption">GOOD DAYS, LITTLE DETOURS.</div>
        <svg className="qt-landscape" viewBox="0 0 540 490" fill="none" aria-hidden="true">
          <circle cx="402" cy="113" r="49" fill="#F7B966" /><path d="M352 42v14m85 0-9 11m44 44h-16" stroke="#DFA059" strokeWidth="3" strokeLinecap="round" />
          <path d="M0 261C87 175 154 211 222 264C306 182 416 191 540 243V490H0Z" fill="#C4DAC9" />
          <path d="M0 342C139 219 267 394 354 280C435 196 496 276 540 317V490H0Z" fill="#84BBA4" />
          <path d="M0 421C111 337 191 389 290 406C390 444 470 324 540 354V490H0Z" fill="#327B66" />
          <path d="M273 490C335 417 240 395 277 347C297 322 368 333 368 288C368 261 333 243 349 219" stroke="#FFF8E8" strokeWidth="28" />
          <path d="m340 222 10-12 10 12" stroke="#155E53" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M73 296v-60h68v60m-80-60 45-33 47 33" stroke="#FFF8E8" strokeWidth="8" strokeLinejoin="round" />
          <path d="M103 293v-30h17v30" stroke="#FFF8E8" strokeWidth="7" />
          <path d="M437 313v-49m-23 24 23-37 24 37z" fill="#155E53" stroke="#155E53" strokeWidth="6" strokeLinejoin="round" />
          <path d="M396 344v-36m-18 18 18-31 18 31z" fill="#155E53" stroke="#155E53" strokeWidth="5" strokeLinejoin="round" />
          <path d="M193 101c12-14 20-14 31 0m0 0c10-14 19-14 30 0" stroke="#598878" strokeWidth="3" strokeLinecap="round" />
          <circle cx="349" cy="198" r="14" fill="#F4A176" stroke="#FFF8E8" strokeWidth="6" />
        </svg>
        <div className="qt-floating-note"><span className="qt-note-icon" aria-hidden="true">☀</span><span>有期待的日子，<br /><strong>从出发开始。</strong></span></div>
        <div className="qt-sample-ticket">
          <div className="qt-ticket-top"><span>一份轻松的出游安排</span><span className="qt-tag">示意</span></div>
          <div className="qt-ticket-stops"><span><i />从住处出发</span><b>→</b><span><i />逛逛喜欢的地方</span><b>→</b><span><i />轻松返程</span></div>
          <div className="qt-ticket-bottom"><span>具体路线，在规划后为你生成</span><span aria-hidden="true">✦</span></div>
        </div>
      </div>
    </section>

    <section className="qt-how qt-container" aria-labelledby="how-title">
      <div><p className="qt-eyebrow">不用做复杂攻略</p><h2 id="how-title">三步，出发更有底。</h2></div>
      <ol className="qt-how-steps">
        <li><span>01</span><div><h3>选一座城市</h3><p>国内慢游，或去国外看看。</p></div></li>
        <li><span>02</span><div><h3>说说你的喜好</h3><p>日期、预算、节奏，都由你定。</p></div></li>
        <li><span>03</span><div><h3>收好每天的安排</h3><p>看地点、看交通，不合适就调整。</p></div></li>
      </ol>
    </section>

    <section className="qt-section qt-container" aria-labelledby="places-title">
      <div className="qt-section-heading"><div><p className="qt-eyebrow">先从喜欢的地方开始</p><h2 id="places-title">一座城市，一种好心情。</h2></div><Link className="qt-text-link" href="/plan/single-city">查看国内外目的地 <span aria-hidden="true">↗</span></Link></div>
      <div className="qt-home-cities">{destinations.map(item => <Link key={item.code} href={`/plan/single-city?city=${item.code}`} className={`qt-home-city qt-tone-${item.tone}`}>
        <div className="qt-postcard-art"><span className="qt-postcard-sun" /><span className="qt-postcard-word" aria-hidden="true">{item.symbol}</span><span className="qt-postcard-lines" /></div>
        <div className="qt-home-city-copy"><h3>{item.name} <span aria-hidden="true">↗</span></h3><p>{item.hint}</p><span className="qt-capability-pill">可选住宿起终点 · 真实交通</span></div>
      </Link>)}</div>
      <p className="qt-small-note">真实交通模式目前支持上述四城的 1–3 天行程，每天最多 3 个主要地点。其他行程可用基础规划。</p>
    </section>

    <section className="qt-reassurance qt-container">
      <div className="qt-reassurance-copy"><p className="qt-eyebrow">玩得开心，也要心里有数</p><h2>把安排看明白，<br />把时间留给风景。</h2><p>晴途帮你整理，不替你冒然决定。<br />行程是参考，出发前记得确认开放时间与预约。</p></div>
      <div className="qt-trust-grid">
        <article><span className="qt-feature-icon" aria-hidden="true">◎</span><h3>信息来源看得见</h3><p>真实地点有来源；估算费用与未核实的信息会注明。</p></article>
        <article><span className="qt-feature-icon" aria-hidden="true">↝</span><h3>每天怎么走，一目了然</h3><p>时间轴搭配地图。支持的城市还能查询实际交通方案。</p></article>
        <article><span className="qt-feature-icon" aria-hidden="true">♡</span><h3>舒服的节奏才重要</h3><p>轻松逛或多走走，自由选择，也可以回到偏好重新安排。</p></article>
      </div>
    </section>

    <section className="qt-secondary-entry qt-container"><div><span className="qt-eyebrow">想一次多看几座城？</span><h2>串起你的下一段旅程。</h2><p>多城市规划是独立的基础模式，功能与单城市不同。</p></div><Link className="qt-button qt-button-outline" href="/plan/multi-city">试试多城市规划 ↗</Link></section>
    <footer className="qt-footer qt-container"><span><strong>晴途 Qingtu</strong> · 把好心情，安排进旅程。</span><Link href="/my-itineraries">我的行程</Link><span className="qt-small-note">Qingtu · 让出发简单一点</span></footer>
  </div>;
}
