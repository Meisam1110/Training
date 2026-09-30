import { ApiError } from "../api/client";
export const fieldErrors = (e: unknown): Record<string, string> => (e instanceof ApiError ? e.fields : {});
export const errMsg = (e: unknown): string => (e instanceof Error ? e.message : "خطای ناشناخته");
export const requiredMsg = (label: string) => `${label} را وارد کنید.`;
