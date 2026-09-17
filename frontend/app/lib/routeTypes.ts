export interface LodgingLocation {
  name: string;
  city_id: number;
  latitude: number;
  longitude: number;
  provider_poi_id?: string;
  coordinate_system: "GCJ02";
}

export interface RoutePoint {
  id: number;
  name: string;
  latitude: number;
  longitude: number;
  verified: boolean;
}

export interface RouteLeg {
  origin: RoutePoint;
  destination: RoutePoint;
  mode: string;
  source: string;
  duration_minutes: number;
  distance_meters: number;
  geometry: number[][][];
  instructions: string[];
  observed_at: string;
  cache_hit: boolean;
  error_code?: string | null;
}

export interface DayRouteSummary {
  lodging: RoutePoint;
  legs: RouteLeg[];
  departure_time: string;
  finish_time: string;
  return_to_lodging: boolean;
  travel_minutes: number;
  distance_meters: number;
  estimated_legs: number;
}

export interface RouteReport {
  status: string;
  warnings: string[];
  unplanned: { id: number; name: string; reason: string }[];
  baseline_travel_minutes: number | null;
  optimized_travel_minutes: number;
  saved_travel_minutes: number | null;
  comparison_scope: string;
}
