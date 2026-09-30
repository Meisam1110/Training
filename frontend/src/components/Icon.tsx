const P: Record<string, string> = {
  home: "M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10",
  calendar: "M4 6h16v14H4zM4 10h16M8 3v4M16 3v4",
  users: "M9 11a3 3 0 100-6 3 3 0 000 6zM3 20c0-3.3 2.7-6 6-6s6 2.7 6 6M17 11a3 3 0 000-6M21 20c0-2.5-1.5-4.6-3.5-5.5",
  mail: "M3 6h18v12H3zM3 7l9 7 9-7",
  file: "M6 3h9l4 4v14H6zM14 3v5h5M9 13h6M9 17h6",
  plug: "M9 3v5M15 3v5M6 8h12v4a6 6 0 01-12 0zM12 18v3",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  download: "M12 4v12M7 11l5 5 5-5M4 20h16",
  shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z",
  menu: "M4 6h16M4 12h16M4 18h16",
  x: "M6 6l12 12M18 6L6 18",
  sun: "M12 16a4 4 0 100-8 4 4 0 000 8zM12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5",
  moon: "M20 14A8 8 0 0110 4a8 8 0 1010 10z",
  check: "M5 12l5 5 9-10",
  alert: "M12 3l10 18H2zM12 10v5M12 18v.5",
  chevron: "M9 6l6 6-6 6",
  chevronDown: "M6 9l6 6 6-6",
  sortUp: "M7 14l5-5 5 5",
  sort: "M8 9l4-4 4 4M8 15l4 4 4-4",
  search: "M11 18a7 7 0 100-14 7 7 0 000 14zM20 20l-4-4",
  eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z",
  eyeOff: "M3 3l18 18M10.6 6.1A9.7 9.7 0 0112 6c6 0 10 6 10 6a17 17 0 01-3 3.6M6.5 7.5C3.8 9.2 2 12 2 12s4 7 10 7c1.5 0 2.9-.4 4.100-1M9.900 9.900a3 3 0 004.200 4.200",
  lock: "M6 11h12v10H6zM8 11V8a4 4 0 018 0v3",
  undo: "M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3",
  refresh: "M20 11a8 8 0 00-14-4M4 4v4h4M4 13a8 8 0 0014 4M20 20v-4h-4",
  plus: "M12 5v14M5 12h14",
  send: "M22 2L11 13M22 2l-7 20-4-9-9-4z",
  logout: "M10 4H4v16h6M16 8l4 4-4 4M20 12H9",
  list: "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  clock: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 7v5l3 2",
  inbox: "M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5",
  book: "M4 4h7a3 3 0 013 3v13a2 2 0 00-2-2H4zM20 4h-7v16h7z",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v5M12 8v.5",
};
export type IconName = keyof typeof P | (string & {});
export function Icon({ name, className = "" }: { name: IconName; className?: string }) {
  return (
    <svg className={`icon ${className}`} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d={P[name] ?? ""} />
    </svg>
  );
}
