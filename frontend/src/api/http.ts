import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { useAppStore } from '../store/useAppStore';
import type { ApiResponse } from '../types';
import { notifyError } from '../utils/feedback';

type RequestConfig = AxiosRequestConfig & { skipGlobalLoading?: boolean; dedupe?: boolean; cacheTtlMs?: number; forceRefresh?: boolean };
type InternalRequestConfig = InternalAxiosRequestConfig & { skipGlobalLoading?: boolean };

interface CachedValue<T> {
  expiresAt: number;
  data: T;
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 60000
});

let pendingCount = 0;
const inFlightGets = new Map<string, Promise<unknown>>();
const memoryCache = new Map<string, CachedValue<unknown>>();
const sessionCachePrefix = 'a-share-api-cache:';

function setLoading(loading: boolean): void {
  useAppStore.getState().setGlobalLoading(loading);
}

function finishLoading(config?: InternalRequestConfig): void {
  if (config?.skipGlobalLoading) return;
  pendingCount = Math.max(0, pendingCount - 1);
  if (pendingCount === 0) setLoading(false);
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  return `{${Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`)
    .join(',')}}`;
}

function requestKey(config: RequestConfig): string {
  return `${(config.method ?? 'GET').toUpperCase()} ${config.url ?? ''} ${stableStringify(config.params ?? {})}`;
}

function readCache<T>(key: string): T | null {
  const now = Date.now();
  const cached = memoryCache.get(key) as CachedValue<T> | undefined;
  if (cached && cached.expiresAt > now) return cached.data;
  memoryCache.delete(key);
  if (typeof sessionStorage === 'undefined') return null;
  try {
    const raw = sessionStorage.getItem(`${sessionCachePrefix}${key}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedValue<T>;
    if (parsed.expiresAt > now) {
      memoryCache.set(key, parsed);
      return parsed.data;
    }
    sessionStorage.removeItem(`${sessionCachePrefix}${key}`);
  } catch {
    try {
      sessionStorage.removeItem(`${sessionCachePrefix}${key}`);
    } catch {
      // Ignore storage cleanup errors.
    }
  }
  return null;
}

function writeCache<T>(key: string, data: T, ttlMs: number): void {
  const cached: CachedValue<T> = { expiresAt: Date.now() + ttlMs, data };
  memoryCache.set(key, cached);
  if (typeof sessionStorage === 'undefined') return;
  try {
    sessionStorage.setItem(`${sessionCachePrefix}${key}`, JSON.stringify(cached));
  } catch {
    // sessionStorage may be full or unavailable; in-memory cache still covers this tab.
  }
}

export function clearRequestCache(fragment?: string): void {
  for (const key of Array.from(memoryCache.keys())) {
    if (!fragment || key.includes(fragment)) memoryCache.delete(key);
  }
  if (typeof sessionStorage === 'undefined') return;
  try {
    for (let index = sessionStorage.length - 1; index >= 0; index -= 1) {
      const key = sessionStorage.key(index);
      if (key?.startsWith(sessionCachePrefix) && (!fragment || key.includes(fragment))) {
        sessionStorage.removeItem(key);
      }
    }
  } catch {
    // Ignore storage access errors.
  }
}

http.interceptors.request.use((config: InternalRequestConfig) => {
  if (!config.skipGlobalLoading) {
    pendingCount += 1;
    setLoading(true);
  }
  useAppStore.getState().setLastError(null);
  return config;
});

http.interceptors.response.use(
  (response) => {
    finishLoading(response.config as InternalRequestConfig);
    const payload = response.data as ApiResponse<unknown>;
    if (payload.code !== 0) {
      const msg = payload.message || '请求失败';
      useAppStore.getState().setLastError(msg);
      notifyError(msg);
      return Promise.reject(new Error(msg));
    }
    return response;
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    finishLoading(error.config as InternalRequestConfig | undefined);
    const msg = error.response?.data?.message ?? error.message ?? '网络错误';
    useAppStore.getState().setLastError(msg);
    notifyError(msg);
    return Promise.reject(error);
  }
);

export async function request<T>(config: RequestConfig): Promise<T> {
  const method = (config.method ?? 'GET').toUpperCase();
  const canReuse = method === 'GET';
  const key = canReuse ? requestKey(config) : '';
  if (canReuse && !config.forceRefresh && config.cacheTtlMs && config.cacheTtlMs > 0) {
    const cached = readCache<T>(key);
    if (cached !== null) {
      useAppStore.getState().setLastError(null);
      return cached;
    }
  }
  if (canReuse && !config.forceRefresh && config.dedupe !== false && inFlightGets.has(key)) {
    return inFlightGets.get(key) as Promise<T>;
  }
  const promise = http.request<ApiResponse<T>>(config).then((response) => {
    const data = response.data.data;
    if (canReuse && config.cacheTtlMs && config.cacheTtlMs > 0) {
      writeCache(key, data, config.cacheTtlMs);
    }
    return data;
  });
  if (canReuse && !config.forceRefresh && config.dedupe !== false) {
    inFlightGets.set(key, promise);
    void promise.then(
      () => inFlightGets.delete(key),
      () => inFlightGets.delete(key)
    );
  }
  return promise;
}

export default http;
