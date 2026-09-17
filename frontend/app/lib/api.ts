/**
 * API client wrapper for making requests to the backend.
 * Automatically includes session ID in headers.
 */

import { getSessionId } from './session';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const API_V1_PREFIX = '/api/v1';

export interface ApiError {
  detail: string;
  field?: string;
}

export class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  /**
   * Get default headers including session ID and optional auth token.
   */
  private getHeaders(authToken?: string): HeadersInit {
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
    };

    const sessionId = getSessionId();
    if (sessionId) {
      headers['X-Session-ID'] = sessionId;
    }

    // Add Authorization header if JWT token is provided
    if (authToken) {
      headers['Authorization'] = `Bearer ${authToken}`;
    }

    return headers;
  }

  /**
   * Make a GET request.
   */
  async get<T>(endpoint: string, authToken?: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${API_V1_PREFIX}${endpoint}`, {
      method: 'GET',
      headers: this.getHeaders(authToken),
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  /**
   * Make a POST request.
   */
  async post<T>(endpoint: string, data?: any, authToken?: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${API_V1_PREFIX}${endpoint}`, {
      method: 'POST',
      headers: this.getHeaders(authToken),
      body: data ? JSON.stringify(data) : undefined,
    });

    if (!response.ok) {
      let errorDetail = 'Request failed';
      try {
        const error: ApiError = await response.json();
        errorDetail = error.detail || JSON.stringify(error);
      } catch (e) {
        errorDetail = `HTTP ${response.status}: ${response.statusText}`;
      }
      console.error('API POST error:', errorDetail);
      throw new Error(errorDetail);
    }

    return response.json();
  }

  /**
   * Make a PUT request.
   */
  async put<T>(endpoint: string, data?: any, authToken?: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${API_V1_PREFIX}${endpoint}`, {
      method: 'PUT',
      headers: this.getHeaders(authToken),
      body: data ? JSON.stringify(data) : undefined,
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  /**
   * Make a DELETE request.
   */
  async delete<T>(endpoint: string, authToken?: string): Promise<T> {
    const response = await fetch(`${this.baseUrl}${API_V1_PREFIX}${endpoint}`, {
      method: 'DELETE',
      headers: this.getHeaders(authToken),
    });

    if (!response.ok) {
      const error: ApiError = await response.json();
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }
}

// Export singleton instance
export const apiClient = new ApiClient();

// Type definitions for API responses
export interface City {
  id: number;
  name: string;
  name_zh?: string | null;
  country: string;
  country_zh?: string | null;
  time_zone?: string;
  default_currency?: string;
  latitude?: number;
  longitude?: number;
  is_domestic?: boolean;
  supports_real_routes?: boolean;
}

export interface Activity {
  id: number;
  name: string;
  name_zh?: string | null;
  category: string;
  cost: number;
  duration: number;
  rating: number;
  coordinates: {
    latitude: number;
    longitude: number;
  };
  tags?: string[] | null;
  description?: string | null;
  description_zh?: string | null;
}

export interface ItineraryBlock {
  start_time: string;
  end_time: string;
  activity: Activity;
  travel_time_from_previous?: number;
  notes?: string;
}

export interface ItineraryDay {
  date: string;
  city_id?: number;
  city_name?: string;
  total_cost: number;
  total_duration_minutes: number;
  blocks: ItineraryBlock[];
}

export interface LegacyDayActivity {
  activity: {
    id: number;
    name: string;
    category: string;
    base_cost: number;
    avg_duration_minutes: number;
    rating: number;
    latitude: number;
    longitude: number;
  };
  start_time: string;
  end_time: string;
  travel_time_minutes?: number;
}

export interface DayPlan {
  day_number: number;
  date: string;
  activities: LegacyDayActivity[];
  total_cost: number;
  total_duration_minutes: number;
}

export interface ItinerarySummary {
  total_cost: number;
  avg_cost_per_day: number;
  categories_covered: string[];
  pace_label: string;
  total_duration_minutes?: number;
  total_activities?: number;
  category_distribution?: Record<string, number>;
  average_rating?: number;
}

export interface NarrativeResult {
  narrative_text: string;
  explanations?: string;
  tips?: string;
}

export interface Itinerary {
  days: ItineraryDay[];
  summary: ItinerarySummary;
  optimization_score?: number;
  confidence_score?: number;
  narrative?: NarrativeResult;
}

export interface TripPreferences {
  destination_city_id?: number;
  start_date: string;
  end_date: string;
  budget_per_day?: number;
  preferred_categories?: string[];
  interests?: string[];
  must_visit_activity_ids?: number[];
  pace?: 'relaxed' | 'moderate' | 'packed';
  start_time?: string;
  end_time?: string;
}

export interface SavedItinerary {
  id: string;
  session_id: string;
  created_at: string;
  updated_at: string;
  is_public: boolean;
  share_token: string | null;
  share_url: string | null;
  view_count: number;
  trip_preferences: TripPreferences;
  itinerary: Itinerary;
}

export interface ItineraryListItem {
  id: string;
  created_at: string;
  city_names: string[];
  start_date: string;
  end_date: string;
  total_cost: number;
  days_count: number;
  is_public: boolean;
  view_count: number;
}

// API methods (without auth - use these when auth token is not available)
export const api = {
  // Cities
  getCities: () => apiClient.get<City[]>('/cities'),

  // Activities
  getActivities: (cityId: number) =>
    apiClient.get<{ activities: Activity[] }>(`/activities?city_id=${cityId}`),

  // Plan itinerary
  planItinerary: (preferences: TripPreferences) =>
    apiClient.post<Itinerary>('/plan-itinerary', preferences),

  // Saved itineraries (these will work better with auth token)
  saveItinerary: (data: any, authToken?: string) => {
    return apiClient.post<SavedItinerary>('/itineraries', data, authToken);
  },

  listItineraries: (authToken?: string) =>
    apiClient.get<ItineraryListItem[]>('/itineraries', authToken),

  getItinerary: (id: string, authToken?: string) =>
    apiClient.get<SavedItinerary>(`/itineraries/${id}`, authToken),

  updateItinerary: (id: string, data: {
    is_public?: boolean;
    trip_preferences?: TripPreferences;
    itinerary?: Itinerary;
  }, authToken?: string) => apiClient.put<SavedItinerary>(`/itineraries/${id}`, data, authToken),

  deleteItinerary: (id: string, authToken?: string) =>
    apiClient.delete<{ message: string }>(`/itineraries/${id}`, authToken),

  shareItinerary: (id: string, authToken?: string) =>
    apiClient.post<{ share_token: string; share_url: string; message: string }>(`/itineraries/${id}/share`, undefined, authToken),

  // Auth
  migrateSession: (authToken: string) =>
    apiClient.post<{ migrated_count: number; message: string }>('/auth/migrate-session', undefined, authToken),

  getSharedItinerary: (token: string) =>
    apiClient.get<SavedItinerary>(`/share/${token}`),
};
