const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN_KEY = "rotom_agent_token";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAccessToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    return;
  }
  localStorage.removeItem(TOKEN_KEY);
}

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getAccessToken();

  if (!headers.has("Content-Type") && options.body) {
    headers.set("Content-Type", "application/json");
  }
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(apiUrl(path), {
    ...options,
    headers,
  });

  if (!response.ok) {
    const message = await readError(response);
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.detail ?? response.statusText;
  } catch {
    return response.statusText;
  }
}
