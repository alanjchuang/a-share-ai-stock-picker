import type { MessageInstance } from 'antd/es/message/interface';

let messageApi: MessageInstance | null = null;

export function setMessageApi(api: MessageInstance): void {
  messageApi = api;
}

export function notifySuccess(content: string): void {
  if (messageApi) {
    void messageApi.success(content);
  } else {
    console.info(content);
  }
}

export function notifyError(content: string): void {
  if (messageApi) {
    void messageApi.error(content);
  } else {
    console.error(content);
  }
}
