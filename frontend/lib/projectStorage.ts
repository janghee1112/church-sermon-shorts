export const PROJECT_STORAGE_KEY = "sermon-shorts-project-id";

export function clearProjectStorage(): void {
  window.localStorage.removeItem(PROJECT_STORAGE_KEY);
}
