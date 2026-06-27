import { create } from 'zustand';
import type { ScreeningRequest, ScreeningResult, ThemeMode, WorkbenchMode } from '../types';

interface AppState {
  themeMode: ThemeMode;
  workbenchMode: WorkbenchMode;
  globalLoading: boolean;
  lastError: string | null;
  currentRequest: ScreeningRequest | null;
  latestResult: ScreeningResult | null;
  setThemeMode: (themeMode: ThemeMode) => void;
  setWorkbenchMode: (workbenchMode: WorkbenchMode) => void;
  setGlobalLoading: (loading: boolean) => void;
  setLastError: (message: string | null) => void;
  setCurrentRequest: (request: ScreeningRequest) => void;
  setLatestResult: (result: ScreeningResult) => void;
}

export const useAppStore = create<AppState>((set) => ({
  themeMode: (localStorage.getItem('a-share-theme') as ThemeMode | null) ?? 'light',
  workbenchMode: (localStorage.getItem('a-share-workbench-mode') as WorkbenchMode | null) ?? 'beginner',
  globalLoading: false,
  lastError: null,
  currentRequest: null,
  latestResult: null,
  setThemeMode: (themeMode) => {
    localStorage.setItem('a-share-theme', themeMode);
    set({ themeMode });
  },
  setWorkbenchMode: (workbenchMode) => {
    localStorage.setItem('a-share-workbench-mode', workbenchMode);
    set({ workbenchMode });
  },
  setGlobalLoading: (globalLoading) => set({ globalLoading }),
  setLastError: (lastError) => set({ lastError }),
  setCurrentRequest: (currentRequest) => set({ currentRequest }),
  setLatestResult: (latestResult) => set({ latestResult })
}));
