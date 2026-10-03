import type { Attendance, ConnectorKind, LetterKind, Role, RunStatus, RunStep, Tri } from "../api/types";
import type { Tone } from "../components/ui";

export const RUN_STATUS_FA: Record<RunStatus, string> = {
  planned: "برنامه‌ریزی‌شده", announced: "اطلاع‌رسانی‌شده", open: "در جریان ثبت‌نام", running: "در حال برگزاری", completed: "برگزار‌شده", cancelled: "لغو‌شده",
};
export const RUN_STATUS_TONE: Record<RunStatus, Tone> = { planned: "neutral", announced: "info", open: "warn", running: "brand", completed: "ok", cancelled: "danger" };
export const STEP_FA: Record<RunStep, string> = {
  plan: "برنامه‌ریزی", candidates: "انتخاب کاندیدا", announce: "اطلاع‌رسانی", motivations: "جمع‌آوری موتیویشن",
  institute_letter: "نامهٔ مؤسسه", settlement: "فاکتور و تسویه", level3: "ارزیابی سطح ۳",
};
export const FLAG_FA: Record<string, string> = {
  over_motivation_limit: "بیش از سقف موتیویشن تأییدنشده", division_change: "تغییر واحد نسبت به IFS", non_active: "کارمند غیرفعال", level3_eligible: "مشمول ارزیابی سطح ۳",
};
export const EXCLUDE_FA: Record<string, string> = { date_overlap: "تداخل زمانی با دورهٔ دیگر" };
export const TRI_FA: Record<Tri, string> = { yes: "بله", no: "خیر", pending: "نامشخص" };
export const TRI_TONE: Record<Tri, Tone> = { yes: "ok", no: "danger", pending: "neutral" };
export const ATT_FA: Record<Attendance, string> = { attended: "حاضر", absent: "غایب", pending: "ثبت نشده" };
export const ATT_TONE: Record<Attendance, Tone> = { attended: "ok", absent: "danger", pending: "neutral" };
export const TYPE_FA = { online: "آنلاین", in_person: "حضوری" };
export const ROLE_FA: Record<Role, string> = { admin: "مدیر سامانه", hr: "کارشناس آموزش", viewer: "ناظر" };
export const LETTER_FA: Record<LetterKind, string> = {
  course_announcement: "اطلاعیهٔ دوره", institute_letter: "نامهٔ مؤسسه", settlement_letter: "نامهٔ تسویه‌حساب",
  level3_request: "درخواست ارزیابی سطح ۳", level3_manager_check: "تأیید مدیر (سطح ۳)", line_manager_approval: "تأیید مدیر مستقیم",
};
export const CONNECTOR_FA: Record<ConnectorKind, string> = { excel: "اکسل (IDP و کارنامهٔ قدیمی)", ifs: "IFS (کارمندان)", smtp: "ایمیل SMTP", graph: "ایمیل Microsoft Graph" };
export const DUE_FA: Record<string, string> = { level3_due: "سررسید ارزیابی سطح ۳", deadline_reminder: "یادآوری مهلت موتیویشن", over3_motivations: "بیش از ۳ موتیویشن تأییدنشده", payment_not_started: "پرداخت آغاز نشده" };
