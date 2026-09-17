"use client";
import { cityLabel } from "./destinationLabels";

interface SelectionExplanationLike {
  category_match?: boolean;
  budget_fit?: string;
  time_fit?: string;
  travel_proximity?: string;
  rating_quality?: string;
  must_visit?: boolean;
  summary?: string;
  semantic_relevance_score?: number | null;
}

const RMB_EXCHANGE_RATES: Record<string, number> = {
  CNY: 1,
  USD: 7.2,
  EUR: 7.9,
  GBP: 9.2,
  JPY: 0.05,
  KRW: 0.0053,
  HKD: 0.92,
  SGD: 5.35,
  THB: 0.2,
  MYR: 1.55,
};

const PLACE_NAME_ALIASES: Record<string, string> = {
  "Tsukiji Outer Market": "筑地场外市场",
  "Senso-ji Temple": "浅草寺",
  "Tokyo Skytree": "东京晴空塔",
  "Meiji Shrine": "明治神宫",
  "Shibuya Crossing": "涩谷十字路口",
  "Harajuku": "原宿",
  "Eiffel Tower": "埃菲尔铁塔",
  "Louvre Museum": "卢浮宫",
  "Golden Gate Bridge": "金门大桥",
  "Statue of Liberty": "自由女神像",
};

const DESCRIPTION_ALIASES: Record<string, string> = {
  "Famous fish market with fresh sushi and street food.": "著名海鲜市场，适合吃新鲜寿司和边走边吃的小吃。",
  "Tokyo's oldest temple in Asakusa.": "东京很有代表性的老寺庙，位于浅草，适合第一次来东京的人打卡。",
  "Tallest structure in Japan with observation decks.": "日本代表性地标之一，可以登高看城市全景。",
  "Shinto shrine dedicated to Emperor Meiji.": "东京很有名的神社，环境安静，适合散步和感受日本神社文化。",
  "World's busiest pedestrian crossing.": "东京非常出名的十字路口，适合拍照和感受城市节奏。",
  "Fashion district known for youth culture.": "东京年轻人文化和潮流购物比较集中的区域。",
};

const TAG_ALIASES: Record<string, string> = {
  budget_friendly: "预算友好",
  outdoor: "户外",
  indoor: "室内",
  highly_rated: "评分高",
  family_friendly: "适合家庭/亲子",
  wheelchair_accessible: "无障碍友好",
};

export function formatChineseDate(dateInput: string | Date, withYear = false): string {
  const date = dateInput instanceof Date ? dateInput : new Date(dateInput);
  return date.toLocaleDateString("zh-CN", {
    weekday: "long",
    month: "long",
    day: "numeric",
    ...(withYear ? { year: "numeric" } : {}),
  });
}

export function formatChineseShortDate(dateInput: string | Date): string {
  const date = dateInput instanceof Date ? dateInput : new Date(dateInput);
  return date.toLocaleDateString("zh-CN", {
    month: "numeric",
    day: "numeric",
  });
}

export function formatChineseWeekday(dateInput: string | Date): string {
  const date = dateInput instanceof Date ? dateInput : new Date(dateInput);
  return date.toLocaleDateString("zh-CN", {
    weekday: "short",
  });
}

export function formatChineseTime(timeInput: string | Date): string {
  const date = timeInput instanceof Date ? timeInput : new Date(timeInput);
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function formatPriceWithRmb(amount: number, currencyCode = "USD"): string {
  const normalizedCurrency = (currencyCode || "USD").toUpperCase();
  const formattedOriginal = `${normalizedCurrency} ${amount.toFixed(0)}`;

  if (normalizedCurrency === "CNY") {
    return `${formattedOriginal}（人民币）`;
  }

  const rate = RMB_EXCHANGE_RATES[normalizedCurrency];
  if (!rate) {
    return formattedOriginal;
  }

  const rmbAmount = amount * rate;
  const rmbText = rmbAmount >= 100
    ? `约 RMB ${rmbAmount.toFixed(0)}`
    : `约 RMB ${rmbAmount.toFixed(1)}`;

  return `${formattedOriginal}（${rmbText}）`;
}

export function getCategoryLabel(category: string): string {
  const labels: Record<string, string> = {
    food: "特色美食",
    culture: "文化与历史",
    nightlife: "夜间体验",
    nature: "公园与自然",
    shopping: "逛街购物",
    adventure: "户外探索",
    beaches: "海边散步",
  };

  return labels[category] || category;
}

export function getLocalizedPlaceName(name: string, nameZh?: string | null): string {
  if (nameZh && nameZh.trim() && nameZh.trim() !== name.trim()) {
    return nameZh;
  }
  const alias = PLACE_NAME_ALIASES[name];
  return alias || name;
}

export function getLocalizedDescription(
  description?: string | null,
  descriptionZh?: string | null
): string | null {
  if (descriptionZh) return descriptionZh;
  if (!description) return null;
  return DESCRIPTION_ALIASES[description] || description;
}

export function getLocalizedCityName(name: string, nameZh?: string | null): string {
  return cityLabel({ name, name_zh: nameZh });
}

export function getLocalizedTag(tag: string): string {
  return TAG_ALIASES[tag] || tag.replaceAll("_", " ");
}

function translateBudgetFit(value?: string): string | null {
  switch (value) {
    case "within budget":
      return "这站的基础花费在你的预算范围内";
    case "slightly over":
      return "这站花费略高一点，但还算能接受";
    case "over budget":
      return "这站偏贵，如果想省钱可以考虑替换";
    default:
      return null;
  }
}

function translateTravelProximity(value?: string): string | null {
  switch (value) {
    case "first activity":
      return "这站被安排成今天的第一站";
    case "nearby (<15min)":
      return "它离上一站比较近，路上不会太折腾";
    case "moderate (15-30min)":
      return "它和上一站距离适中，顺路程度还可以";
    case "far (>30min)":
      return "它和上一站有点远，是今天相对更费路程的一站";
    default:
      return null;
  }
}

function translateRatingQuality(value?: string): string | null {
  switch (value) {
    case "excellent (4.5+)":
      return "它的用户评分很高";
    case "good (3.5+)":
      return "它的评分整体不错";
    case "average":
      return "它的评分中等";
    case "below average":
      return "它的评分一般，不算特别强";
    default:
      return null;
  }
}

function translateTimeFit(value?: string): string | null {
  switch (value) {
    case "fits perfectly":
      return "停留时长和你这一天的节奏比较匹配";
    case "tight fit":
      return "这站时间上稍微有点紧，但还能塞进今天";
    case "too long":
      return "这站本来比较耗时间，当前安排有点赶";
    default:
      return null;
  }
}

export function getLocalizedSelectionReason(
  explanation?: SelectionExplanationLike | null,
  category?: string
): string {
  if (!explanation) {
    return "系统主要按顺路程度、评分、预算和你的偏好，把今天的地点尽量排得更顺。";
  }

  const reasons: string[] = [];
  if (explanation.must_visit) {
    reasons.push("这是你特别想去的地点");
  }
  if (explanation.category_match && category) {
    reasons.push(`它符合你偏好的${getCategoryLabel(category)}`);
  }

  const travel = translateTravelProximity(explanation.travel_proximity);
  const rating = translateRatingQuality(explanation.rating_quality);
  const budget = translateBudgetFit(explanation.budget_fit);
  const timeFit = translateTimeFit(explanation.time_fit);

  if (travel) reasons.push(travel);
  if (rating) reasons.push(rating);
  if (budget) reasons.push(budget);
  if (timeFit) reasons.push(timeFit);

  return reasons.length > 0
    ? reasons.join("；")
    : "系统主要根据顺路、评分、预算和你的偏好来选这站。";
}
