/**
 * Zustand store for managing itinerary state across the application.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { ITINERARY_STORAGE_KEY, LEGACY_ITINERARY_STORAGE_KEY, readBrandedStorage } from '../lib/brandedStorage';
import type { Itinerary, TripPreferences, SavedItinerary, ItineraryListItem } from '../lib/api';

interface ItineraryState {
  // Current itinerary generation
  currentPreferences: TripPreferences | null;
  currentItinerary: Itinerary | null;
  isGenerating: boolean;
  generationError: string | null;

  // Saved itineraries
  savedItineraries: ItineraryListItem[];
  currentSavedId: string | null;

  // Actions
  setCurrentPreferences: (preferences: TripPreferences | null) => void;
  setCurrentItinerary: (itinerary: Itinerary | null) => void;
  setIsGenerating: (isGenerating: boolean) => void;
  setGenerationError: (error: string | null) => void;

  setSavedItineraries: (itineraries: ItineraryListItem[]) => void;
  setCurrentSavedId: (id: string | null) => void;

  clearCurrent: () => void;
  reset: () => void;
}

export const useItineraryStore = create<ItineraryState>()(
  persist(
    (set) => ({
      // Initial state
      currentPreferences: null,
      currentItinerary: null,
      isGenerating: false,
      generationError: null,
      savedItineraries: [],
      currentSavedId: null,

      // Actions
      setCurrentPreferences: (preferences) =>
        set({ currentPreferences: preferences }),

      setCurrentItinerary: (itinerary) =>
        set({ currentItinerary: itinerary }),

      setIsGenerating: (isGenerating) =>
        set({ isGenerating }),

      setGenerationError: (error) =>
        set({ generationError: error }),

      setSavedItineraries: (itineraries) =>
        set({ savedItineraries: itineraries }),

      setCurrentSavedId: (id) =>
        set({ currentSavedId: id }),

      clearCurrent: () =>
        set({
          currentPreferences: null,
          currentItinerary: null,
          isGenerating: false,
          generationError: null,
          currentSavedId: null,
        }),

      reset: () =>
        set({
          currentPreferences: null,
          currentItinerary: null,
          isGenerating: false,
          generationError: null,
          savedItineraries: [],
          currentSavedId: null,
        }),
    }),
    {
      name: ITINERARY_STORAGE_KEY,
      storage: createJSONStorage(() => ({
        getItem: (key) => typeof window === 'undefined' ? null : readBrandedStorage(localStorage, key, LEGACY_ITINERARY_STORAGE_KEY),
        setItem: (key, value) => { if (typeof window !== 'undefined') localStorage.setItem(key, value); },
        removeItem: (key) => {
          if (typeof window !== 'undefined') {
            localStorage.removeItem(key);
            localStorage.removeItem(LEGACY_ITINERARY_STORAGE_KEY);
          }
        },
      })),
      // Only persist saved itineraries list, not the current generation
      partialize: (state) => ({
        savedItineraries: state.savedItineraries,
      }),
    }
  )
);

// Selectors for easy access
export const selectCurrentItinerary = (state: ItineraryState) => state.currentItinerary;
export const selectCurrentPreferences = (state: ItineraryState) => state.currentPreferences;
export const selectIsGenerating = (state: ItineraryState) => state.isGenerating;
export const selectGenerationError = (state: ItineraryState) => state.generationError;
export const selectSavedItineraries = (state: ItineraryState) => state.savedItineraries;
export const selectCurrentSavedId = (state: ItineraryState) => state.currentSavedId;
