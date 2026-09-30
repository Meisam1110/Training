/**
 * PLACEHOLDER brand mark. No Irancell logo asset exists in this repo, so this is a neutral
 * yellow tile + product name. To use the official logo, replace the body of <BrandMark/>
 * with an <img src={logoUrl} alt=""/> (or inline SVG) — nothing else depends on it.
 */
export function BrandMark({ size = 36 }: { size?: number }) {
  return (
    <span className="wordmark__mark" style={{ inlineSize: size, blockSize: size }} aria-hidden="true">
      <svg viewBox="0 0 32 32" width={size * 0.62} height={size * 0.62} fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 24V8l10 12L26 8v16" />
      </svg>
    </span>
  );
}
export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="wordmark" role="img" aria-label="سامانه مدیریت آموزش">
      <BrandMark />
      {!compact && (
        <span className="wordmark__text">
          مدیریت آموزش
          <small>توسعه استعداد · منابع انسانی</small>
        </span>
      )}
    </span>
  );
}
