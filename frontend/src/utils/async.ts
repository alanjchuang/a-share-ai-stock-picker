export function runSafely(task: Promise<unknown>): void {
  void task.catch(() => undefined);
}
