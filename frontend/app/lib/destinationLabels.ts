export const CITY_LABELS: Record<string, string> = {
  Beijing: "北京", Shanghai: "上海", Hangzhou: "杭州", Chengdu: "成都",
  "San Francisco": "旧金山", Paris: "巴黎", "New York": "纽约", London: "伦敦",
  Tokyo: "东京", Rome: "罗马", Barcelona: "巴塞罗那", Sydney: "悉尼", Dubai: "迪拜",
};
export const CITY_HINTS: Record<string, string> = {
  Beijing: "古都里，发现新故事", Shanghai: "沿着街区，慢慢逛", Hangzhou: "把时间留给湖畔", Chengdu: "吃好逛好，慢一点也好",
};
export function cityLabel(city: { name: string; name_zh?: string | null }): string {
  return city.name_zh && city.name_zh !== city.name ? city.name_zh : CITY_LABELS[city.name] || city.name;
}
