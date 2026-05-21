import { request } from "./http";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: string;
  email: string;
  display_name: string;
  status: string;
  default_workspace_id: string | null;
}

export function login(payload: LoginRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function register(payload: RegisterRequest): Promise<TokenResponse> {
  return request<TokenResponse>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getMe(): Promise<UserResponse> {
  return request<UserResponse>("/api/auth/me");
}
