"""LLM narrative generator for itineraries."""
from app.llm.client import LLMClient
from app.api.schemas import TripPreferences, NarrativeResult
from app.core.optimizer import Itinerary, get_activities_per_day


def format_itinerary_for_llm(itinerary: Itinerary) -> str:
    """Format itinerary data into a compact string for LLM."""
    lines = []
    
    if itinerary.summary:
        lines.append(f"Trip Summary:")
        lines.append(f"- Total Cost: ${itinerary.summary.total_cost:.2f}")
        lines.append(f"- Average Cost per Day: ${itinerary.summary.avg_cost_per_day:.2f}")
        lines.append(f"- Categories Covered: {', '.join(itinerary.summary.categories_covered)}")
        lines.append(f"- Pace: {itinerary.summary.pace_label}")
        lines.append("")
    
    for day in itinerary.days:
        lines.append(f"Day {day.date}:")
        if day.route_summary:
            lines.append(f"交通参考 {day.route_summary['travel_minutes']} 分钟；结束/返回住宿时间 {day.route_summary['finish_time']}。路线方案为查询时快照，不保证未来班次。")
        for i, block in enumerate(day.blocks):
            time_str = block.start_time.split("T")[1][:5]  # Extract time
            lines.append(
                f"  {time_str} - {block.activity.name_zh or block.activity.name} ({block.activity.category})"
            )
            if block.travel_time_from_previous:
                lines.append(f"    (Travel time: {block.travel_time_from_previous} minutes)")
            if block.activity.poi_source:
                lines.append("    地点来自高德；金额是人均消费参考或类别估算，不是已核验门票。停留时长为估算，未来开放时间和预约状态未知。")
        lines.append("")
    
    return "\n".join(lines)


def format_preferences_for_llm(preferences: TripPreferences) -> str:
    """Format user preferences into a string for LLM."""
    lines = []
    lines.append("User Preferences:")
    lines.append(f"- Trip Type: {preferences.trip_type.value}")
    lines.append(f"- Budget Level: {preferences.budget_level.value}")
    if preferences.budget_per_day:
        lines.append(f"- Budget per Day: ${preferences.budget_per_day:.2f}")
    lines.append(f"- Energy Level: {preferences.energy_level.value}")
    lines.append(f"- Travel Mode: {preferences.travel_mode.value}")
    
    if preferences.preferred_categories:
        categories = [cat.value for cat in preferences.preferred_categories]
        lines.append(f"- Preferred Categories: {', '.join(categories)}")
    
    if preferences.constraints:
        if preferences.constraints.must_visit:
            lines.append(f"- Must Visit: {', '.join(preferences.constraints.must_visit)}")
        if preferences.constraints.avoid:
            lines.append(f"- Avoid: {', '.join(preferences.constraints.avoid)}")
        if preferences.constraints.dietary_preferences:
            lines.append(f"- Dietary: {preferences.constraints.dietary_preferences}")
    
    return "\n".join(lines)


async def generate_narrative(
    itinerary: Itinerary, preferences: TripPreferences
) -> NarrativeResult:
    """
    Generate narrative text for an itinerary using LLM.
    
    Args:
        itinerary: The optimized itinerary
        preferences: User trip preferences
    
    Returns:
        NarrativeResult with narrative text, explanations, and tips
    """
    client = LLMClient()
    
    system_prompt = """你是一名中文旅行助手。请用简洁、自然的中文输出一段行程解读：
1. 先用 3 到 4 句话概括这趟旅行的整体风格和亮点；
2. 再补充 2 到 3 条实用建议；
3. 不要逐天复述完整日程，因为页面里已经展示了详细安排；
4. 风格友好、简洁、像真的旅行顾问，不要写得太空泛。
5. 只能解释已提供的安排，不得声称路线是最短路线，不得编造实时路况、天气或预约信息。
6. 没有安排景点的日期应说明自由活动，不要编造景点填满。"""

    itinerary_text = format_itinerary_for_llm(itinerary)
    preferences_text = format_preferences_for_llm(preferences)

    user_prompt = f"""以下是本次旅行信息：
{preferences_text}

{itinerary_text}

请输出中文内容：
1. 一段 3 到 4 句的整体解读，说明这趟行程适合怎样体验；
2. 2 到 3 条简短实用建议，可以涉及出发时间、穿着、预算、用餐、交通或当地习惯；

总长度尽量控制在 150 字左右，不要按天逐条复述。"""
    
    # Generate narrative
    narrative_text = await client.generate_completion(system_prompt, user_prompt)
    minimum, _ = get_activities_per_day(preferences.energy_level)
    if any(len(day.blocks) < minimum for day in itinerary.days):
        narrative_text = (
            "规划提示：受当前景点数量、预算或开放时间限制，部分日期安排较少；"
            "已避免跨天重复景点，空余时间可自由活动。\n\n" + narrative_text
        )
    
    # For now, we'll put everything in narrative_text
    # In a more advanced version, we could parse the LLM response to extract
    # separate explanations and tips sections
    
    return NarrativeResult(
        narrative_text=narrative_text,
        explanations=None,  # Could be extracted from LLM response
        tips=None,  # Could be extracted from LLM response
        source="fallback" if client.failure_code else "ai",
        provider="deepseek" if client.using_deepseek else "openai",
        error_code=client.failure_code,
    )

