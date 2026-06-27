import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { useAppStore } from '../store/useAppStore';
import type { ApiResponse } from '../types';
import { notifyError } from '../utils/feedback';

type RequestConfig = AxiosRequestConfig & { skipGlobalLoading?: boolean };
type InternalRequestConfig = InternalAxiosRequestConfig & { skipGlobalLoading?: boolean };

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 60000
});

let pendingCount = 0;

function setLoading(loading: boolean): void {
  useAppStore.getState().setGlobalLoading(loading);
}

function finishLoading(config?: InternalRequestConfig): void {
  if (config?.skipGlobalLoading) return;
  pendingCount = Math.max(0, pendingCount - 1);
  if (pendingCount === 0) setLoading(false);
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
  const response = await http.request<ApiResponse<T>>(config);
  return response.data.data;
}

export default http;
