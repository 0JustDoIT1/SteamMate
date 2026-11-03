import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/** 조건부 클래스 결합 + Tailwind 충돌 클래스 정리(shadcn 컴포넌트 공용). */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
