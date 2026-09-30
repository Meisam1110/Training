import type { ReactNode } from "react";
import type { IconName } from "./components/Icon";
import { LoginScreen } from "./screens/Login";
import { DashboardScreen } from "./screens/Dashboard";
import { RunsScreen, RunDetailScreen } from "./screens/Runs";
import { CandidatesScreen } from "./screens/Candidates";
import { EnrollmentsScreen } from "./screens/Enrollments";
import { LettersScreen } from "./screens/Letters";
import { EmployeesScreen } from "./screens/Employees";
import { ConnectorsScreen } from "./screens/Connectors";
import { AutomationScreen } from "./screens/Automation";
import { ImportExportScreen } from "./screens/ImportExport";
import { AdminScreen } from "./screens/Admin";

export interface NavItem { path: string; title: string; icon: IconName; group: string; admin?: boolean; hr?: boolean }
export const NAV: NavItem[] = [
  { path: "/", title: "داشبورد", icon: "home", group: "کار روزانه" },
  { path: "/runs", title: "دوره‌های آموزشی", icon: "calendar", group: "کار روزانه" },
  { path: "/enrollments", title: "ثبت‌نام‌ها", icon: "list", group: "کار روزانه" },
  { path: "/letters", title: "مرکز نامه‌ها", icon: "mail", group: "کار روزانه" },
  { path: "/employees", title: "کارمندان", icon: "users", group: "داده‌ها" },
  { path: "/import-export", title: "درون‌ریزی و برون‌بری", icon: "upload", group: "داده‌ها", hr: true },
  { path: "/connectors", title: "اتصال‌ها", icon: "plug", group: "سیستم", hr: true },
  { path: "/automation", title: "خودکارسازی", icon: "bolt", group: "سیستم" },
  { path: "/admin", title: "مدیریت", icon: "shield", group: "سیستم", admin: true },
];

export interface RouteDef { pattern: string; title: string; render: (p: Record<string, string>) => ReactNode; public?: boolean; admin?: boolean; hr?: boolean }
export const ROUTES: RouteDef[] = [
  { pattern: "/login", title: "ورود", render: () => <LoginScreen />, public: true },
  { pattern: "/", title: "داشبورد", render: () => <DashboardScreen /> },
  { pattern: "/runs", title: "دوره‌های آموزشی", render: () => <RunsScreen /> },
  { pattern: "/runs/:id", title: "جزئیات دوره", render: (p) => <RunDetailScreen id={Number(p.id)} /> },
  { pattern: "/runs/:id/candidates", title: "انتخاب کاندیدا", render: (p) => <CandidatesScreen id={Number(p.id)} /> },
  { pattern: "/enrollments", title: "ثبت‌نام‌ها", render: () => <EnrollmentsScreen /> },
  { pattern: "/letters", title: "مرکز نامه‌ها", render: () => <LettersScreen /> },
  { pattern: "/employees", title: "کارمندان", render: () => <EmployeesScreen /> },
  { pattern: "/connectors", title: "اتصال‌ها", render: () => <ConnectorsScreen />, hr: true },
  { pattern: "/automation", title: "خودکارسازی", render: () => <AutomationScreen /> },
  { pattern: "/import-export", title: "درون‌ریزی و برون‌بری", render: () => <ImportExportScreen />, hr: true },
  { pattern: "/admin", title: "مدیریت", render: () => <AdminScreen />, admin: true },
];
