/** Auth-related types mirroring the backend schemas (app/schemas/auth.py). */

export type UserRole = "donor" | "organization" | "admin";
export type AccountStatus = "active" | "inactive" | "suspended";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  status: AccountStatus;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export type RegisterRole = "donor" | "organization";

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
  role: RegisterRole;
}
