"""Pydantic schemas for API requests and responses."""
from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Optional, List, Literal
from datetime import date, time
from enum import Enum


# Enums
class TripType(str, Enum):
    day_trip = "day_trip"
    weekend = "weekend"
    one_week = "one_week"
    long = "long"


class BudgetLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Category(str, Enum):
    food = "food"
    culture = "culture"
    nightlife = "nightlife"
    nature = "nature"
    shopping = "shopping"
    adventure = "adventure"
    beaches = "beaches"


class EnergyLevel(str, Enum):
    relaxed = "relaxed"
    moderate = "moderate"
    active = "active"


class TravelMode(str, Enum):
    walking = "walking"
    public_transport = "public_transport"
    taxi = "taxi"
    self_drive = "self_drive"
    mixed = "mixed"


class WalkingTolerance(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


# Input Schemas
class Constraints(BaseModel):
    must_visit: Optional[List[str]] = Field(default=[], description="Activity names that must be included")
    avoid: Optional[List[str]] = Field(default=[], description="Activity names to avoid")
    dietary_preferences: Optional[str] = Field(default=None, description="Dietary restrictions or preferences")
    walking_tolerance: Optional[WalkingTolerance] = Field(default=None, description="Walking tolerance level")


class CitySegment(BaseModel):
    """City segment for multi-city trips."""
    city_id: int
    stay_duration_days: int = Field(gt=0, description="Number of days to stay in this city")
    travel_time_from_previous_hours: Optional[int] = Field(default=None, description="Travel time from previous city in hours")


class LodgingLocation(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    city_id: int = Field(gt=0)
    latitude: float = Field(ge=18, le=54)
    longitude: float = Field(ge=73, le=135)
    provider_poi_id: Optional[str] = None
    coordinate_system: Literal["GCJ02"] = "GCJ02"


class TripPreferences(BaseModel):
    start_date: date
    end_date: date
    # Support both single city (backward compatible) and multi-city
    destination_city_id: Optional[int] = Field(default=None, description="Single city ID (for backward compatibility)")
    city_segments: Optional[List[CitySegment]] = Field(default=None, description="Multi-city trip segments")
    trip_type: TripType
    budget_level: BudgetLevel
    budget_per_day: Optional[float] = Field(default=None, description="Optional numeric budget per day")
    preferred_categories: List[Category] = Field(default=[], description="Preferred activity categories")
    energy_level: EnergyLevel
    travel_mode: TravelMode
    constraints: Optional[Constraints] = Field(default=None)
    use_real_routes: bool = False
    lodging: Optional[LodgingLocation] = None
    daily_start_time: str = Field(default="10:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    daily_end_time: str = Field(default="20:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    return_to_lodging: bool = True

    @model_validator(mode="after")
    def validate_route_preferences(self):
        if self.use_real_routes:
            if not self.lodging or self.lodging.city_id != self.destination_city_id or self.city_segments:
                raise ValueError("真实路线模式需要选择当前城市的住宿起点，且仅支持单城市")
            if self.daily_end_time <= self.daily_start_time:
                raise ValueError("每日结束时间必须晚于出发时间，暂不支持跨夜")
            if not 1 <= (self.end_date - self.start_date).days + 1 <= 3:
                raise ValueError("真实路线首版支持1至3天；更长行程请使用常规规划")
        return self
    
    def get_city_ids(self) -> List[int]:
        """Get list of city IDs from either single city or multi-city segments."""
        if self.city_segments:
            return [seg.city_id for seg in self.city_segments]
        elif self.destination_city_id:
            return [self.destination_city_id]
        else:
            raise ValueError("Either destination_city_id or city_segments must be provided")


# Output Schemas
class Coordinates(BaseModel):
    latitude: float
    longitude: float


class SelectionExplanation(BaseModel):
    """Structured reasoning for why an activity was selected."""
    category_match: bool
    semantic_relevance_score: Optional[float] = Field(default=None, description="Cosine similarity score from RAG (0-1)")
    budget_fit: str = Field(description="'within budget' | 'slightly over' | 'over budget'")
    time_fit: str = Field(description="'fits perfectly' | 'tight fit' | 'too long'")
    travel_proximity: str = Field(description="'nearby (<15min)' | 'moderate (15-30min)' | 'far (>30min)' | 'first activity'")
    rating_quality: str = Field(description="'excellent (4.5+)' | 'good (3.5+)' | 'average' | 'below average'")
    must_visit: bool = Field(default=False)
    summary: str = Field(description="One-sentence human-readable reason for selection")


class ActivitySummary(BaseModel):
    id: int
    name: str
    name_zh: Optional[str] = None
    category: str
    cost: float
    duration: int  # minutes
    rating: float
    coordinates: Coordinates
    tags: Optional[List[str]] = Field(default=None, description="Activity tags like family_friendly, wheelchair_accessible")
    description: Optional[str] = Field(default=None, description="Activity description")
    description_zh: Optional[str] = Field(default=None, description="Chinese activity description")
    explanation: Optional[SelectionExplanation] = Field(default=None, description="Why this activity was chosen")
    poi_source: Optional[dict] = None

    class Config:
        from_attributes = True


class ItineraryBlock(BaseModel):
    start_time: str  # ISO time string
    end_time: str
    activity: ActivitySummary
    travel_time_from_previous: Optional[int] = Field(default=None, description="Travel time in minutes")
    notes: Optional[str] = None


class ItineraryDay(BaseModel):
    date: date
    city_id: Optional[int] = Field(default=None, description="City ID for this day (for multi-city trips)")
    city_name: Optional[str] = Field(default=None, description="City name for this day (for multi-city trips)")
    total_cost: float
    total_duration_minutes: int
    blocks: List[ItineraryBlock]
    route_summary: Optional[dict] = None


class ItinerarySummary(BaseModel):
    total_cost: float
    avg_cost_per_day: float
    categories_covered: List[str]
    pace_label: str


class NarrativeResult(BaseModel):
    narrative_text: str
    explanations: Optional[str] = None
    tips: Optional[str] = None
    source: Optional[str] = None
    provider: Optional[str] = None
    error_code: Optional[str] = None


class ItineraryResponse(BaseModel):
    days: List[ItineraryDay]
    summary: ItinerarySummary
    optimization_score: float = Field(description="Score from 0-1 indicating itinerary quality")
    confidence_score: float = Field(description="Confidence in recommendations from 0-1")
    narrative: NarrativeResult
    poi_search: Optional[dict] = None
    route_report: Optional[dict] = None


class CityResponse(BaseModel):
    id: int
    name: str
    name_zh: Optional[str] = None
    country: str
    country_zh: Optional[str] = None
    time_zone: str
    default_currency: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_domestic: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def supports_real_routes(self) -> bool:
        from app.core.route_cities import supports_real_routes
        return supports_real_routes(self.name, self.is_domestic)

    class Config:
        from_attributes = True


# Saved Itinerary Schemas
class SaveItineraryRequest(BaseModel):
    """Request to save a generated itinerary."""
    trip_preferences: TripPreferences
    itinerary: ItineraryResponse
    is_public: bool = Field(default=False, description="Make itinerary publicly viewable")


class SavedItineraryResponse(BaseModel):
    """Response after saving an itinerary."""
    id: str  # UUID
    session_id: str
    created_at: str  # ISO datetime
    updated_at: str
    is_public: bool
    share_token: Optional[str] = Field(default=None, description="Token for public sharing")
    share_url: Optional[str] = Field(default=None, description="Full URL for sharing")
    view_count: int
    trip_preferences: TripPreferences
    itinerary: ItineraryResponse


class ItineraryListItem(BaseModel):
    """Summary of a saved itinerary for list views."""
    id: str
    created_at: str
    city_names: List[str]
    start_date: str
    end_date: str
    total_cost: float
    days_count: int
    is_public: bool
    view_count: int


class UpdateItineraryRequest(BaseModel):
    """Request to update an existing itinerary."""
    is_public: Optional[bool] = None
    trip_preferences: Optional[TripPreferences] = None
    itinerary: Optional[ItineraryResponse] = None


# --- Refinement Schemas ---

class RefinementIntent(BaseModel):
    """Structured intent extracted by LLM from a natural language refinement request."""
    action: str = Field(description="'replace' | 'add' | 'remove' | 'reschedule'")
    target_day: Optional[int] = Field(default=None, description="1-indexed day number to modify")
    target_activity_name: Optional[str] = Field(default=None, description="Name of activity to replace/remove")
    desired_categories: List[str] = Field(default=[], description="Categories user wants instead")
    avoid_categories: List[str] = Field(default=[], description="Categories to avoid")
    preferred_time_window: Optional[str] = Field(default=None, description="e.g. 'morning', 'afternoon', 'evening'")
    replacement_candidates: List[str] = Field(default=[], description="Suggested activity names from LLM")
    venue_search_query: Optional[str] = Field(default=None, description="Google Places search query capturing exactly what the user wants")
    explanation: str = Field(description="LLM's interpretation of the user's request")


class RefineRequest(BaseModel):
    """Request to refine an existing itinerary via natural language."""
    itinerary: ItineraryResponse
    preferences: TripPreferences
    user_message: str = Field(description="Natural language refinement request from user")


class VenueAlternative(BaseModel):
    """A real-world venue alternative from Google Places."""
    name: str
    category: str
    rating: float
    address: str
    latitude: float
    longitude: float
    cost: float
    price_label: str
    place_id: str
    source: str = "google_places"


class RefineResponse(BaseModel):
    """Response after applying a refinement."""
    itinerary: ItineraryResponse
    changes_made: List[str] = Field(description="Human-readable list of changes applied")
    assistant_message: str = Field(description="Summary message to show the user")
    refinement_intent: RefinementIntent = Field(description="Parsed intent — for transparency and debugging")
    alternatives: Optional[List[VenueAlternative]] = Field(default=None, description="Other real venues the user could swap in instead")


# --- Agent Schemas ---

class AgentToolCall(BaseModel):
    """A single tool call made by the agent during planning."""
    tool_name: str
    arguments: dict
    result: Optional[str] = None
    status: str = "ok"
    candidate_ids: List[int] = Field(default_factory=list)


class AgentPlanRequest(BaseModel):
    """Request to plan an itinerary via the agent orchestration layer."""
    preferences: TripPreferences
    user_message: Optional[str] = Field(default=None, max_length=2000)


class AgentPlanResponse(BaseModel):
    """Response from the agent planner with full reasoning trace."""
    itinerary: ItineraryResponse
    agent_trace: List[AgentToolCall] = Field(description="Full sequence of tool calls made by the agent")
    tokens_used: int = Field(description="Agent decision tokens reported by provider; excludes narrative and embeddings")
    provider: Optional[str] = None
    model: Optional[str] = None
    candidate_ids: List[int] = Field(default_factory=list)
    termination_reason: str = "optimized"

