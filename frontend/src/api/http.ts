import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';
import { useAppStore } from '../store/useAppStore';
import type { ApiResponse } from '../types';

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 60000
});

let pendingCount = 0;

function setLoading(loading: boolean): void {
  useAppStore.getState().setGlobalLoading(loading);
}

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  pendingCount += 1;
  setLoading(true);
  return config;
});

http.interceptors.response.use(
  (response) => {
    pendingCount = Math.max(0, pendingCount - 1);
    if (pendingCount === 0) setLoading(false);
    const payload = response.data as ApiResponse<unknown>;
    if (payload.code !== 0) {
      message.error(payload.message || '请求失败');
      return Promise.reject(new Error(payload.message));
    }
    return response;
  },
  (error: AxiosError<ApiResponse<unknown>>) => {
    pendingCount = Math.max(0, pendingCount - 1);
    if (pendingCount === 0) setLoading(false);
    const msg = error.response?.data?.message ?? error.message ?? '网络错误';
    message.error(msg);
    return Promise.reject(error);
  }
);

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const response = await http.request<ApiResponse<T>>(config);
  return response.data.data;
}

export default http;
