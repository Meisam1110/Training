export interface ThemeTokens { [name: string]: string }
export function buildTokens(json: unknown): { css: string; light: ThemeTokens; dark: ThemeTokens };
export function contrast(a: string, b: string): number;
export function mix(a: string, b: string, pctOfA: number): string;
