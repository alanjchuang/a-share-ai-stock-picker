import { create } from 'zustand';
import type { ScreeningRequest, ScreeningResult, ThemeMode } from '../types';

interface AppState {
  themeMode: ThemeMode;
  globalLoading: boolean;
  currentRequest: ScreeningRequest | null;
  latestResult: ScreeningResult | null;
  setThemeMode: (themeMode: ThemeMode) => void;
  setGlobalLoading: (loading: boolean) => void;
  setCurrentRequest: (request: ScreeningRequest) => void;
  setLatestResult: (result: ScreeningResult) => void;
}

export const useAppStore = create<AppState>((set) => ({
  themeMode: (localStorage.getItem('a-share-theme') as ThemeMode | null) ?? 'light',
  globalLoading: false,
  currentRequest: null,
  latestResult: null,
  setThemeMode: (themeMode) => {
    localStorage.setItem('a-share-theme', themeMode);
    set({ themeMode });
  },
  setGlobalLoading: (globalLoading) => set({ globalLoading }),
  setCurrentRequest: (currentRequest) => set({ currentRequest }),
  setLatestResult: (latestResult) => set({ latestResult })
}));
