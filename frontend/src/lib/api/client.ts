import type { components } from "./schema";

export type Schemas = components["schemas"];

// 백엔드 공통 오류 형식: {"error": {"code", "message"}}
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** 같은 출처의 /api 프록시로 요청한다(세션 쿠키 자동 포함). */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { credentials: "same-origin", ...init });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "서버에 연결할 수 없습니다.");
  }

  if (res.ok) {
    return (res.status === 204 ? undefined : await res.json()) as T;
  }

  const body = await res.json().catch(() => null);
  const error = body?.error;
  throw new ApiError(
    res.status,
    typeof error?.code === "string" ? error.code : "UNKNOWN_ERROR",
    typeof error?.message === "string" ? error.message : "요청을 처리하지 못했습니다.",
  );
}
