import { bug } from "./bugs";

export type Booking = {
  id: string;
  roomId: number;
  guest: string;
  checkIn: string;
  checkOut: string;
  total: number;
};

const DAY_MS = 24 * 60 * 60 * 1000;

/** Nights between two yyyy-mm-dd dates; 0 or less when check-out isn't after check-in. */
export function nights(checkIn: string, checkOut: string): number {
  if (!checkIn || !checkOut) return 0;
  return Math.round((Date.parse(checkOut) - Date.parse(checkIn)) / DAY_MS);
}

/** What the stay costs. */
export function stayTotal(rate: number, nightCount: number): number {
  // Bug 3: the number of nights is ignored.
  if (bug(3)) return nightCount > 0 ? rate : 0;
  return rate * Math.max(nightCount, 0);
}

export type BookingForm = { guest: string; email: string; checkIn: string; checkOut: string };
export type FormErrors = Partial<Record<keyof BookingForm, string>>;

/** The dates the room can be booked, from the availability API; null when it isn't known. */
export type OpenWindow = { from: string; to: string };

/** The availability API's answer as a window, or null (an error, or an unexpected shape). */
export function openWindow(data: unknown): OpenWindow | null {
  const d = data as { openFrom?: unknown; openTo?: unknown } | null;
  return typeof d?.openFrom === "string" && typeof d?.openTo === "string" ? { from: d.openFrom, to: d.openTo } : null;
}

/** Today as yyyy-mm-dd, the format of the date inputs. */
export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export type DateRules = { today?: string; open?: OpenWindow | null };

export function validate(form: BookingForm, rules: DateRules = {}): FormErrors {
  const errors: FormErrors = {};
  const today = rules.today ?? todayIso();
  if (!form.guest.trim()) errors.guest = "Enter the guest's name.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errors.email = "Enter a valid email address.";
  if (!form.checkIn) errors.checkIn = "Choose a check-in date.";
  // Run 7 (benchmark v2), both builds: a stay can't start in the past.
  else if (form.checkIn < today) errors.checkIn = "Check-in can't be in the past.";
  if (!form.checkOut) errors.checkOut = "Choose a check-out date.";
  // Bug 4: a check-out before check-in is let through.
  else if (!bug(4) && nights(form.checkIn, form.checkOut) <= 0) {
    errors.checkOut = "Check-out must be after check-in.";
  }
  // Run 7 (benchmark v2), both builds: the stay must fall inside the room's open dates. Only when
  // they are known: the buggy build's availability API fails on purpose (bug 1), and blocking
  // every booking there would hide the planted booking bugs behind it.
  if (rules.open) {
    const message = "This room is open from " + rules.open.from + " to " + rules.open.to + ".";
    if (form.checkIn && !errors.checkIn && form.checkIn < rules.open.from) errors.checkIn = message;
    if (form.checkOut && !errors.checkOut && form.checkOut > rules.open.to) errors.checkOut = message;
  }
  return errors;
}

/** The errors left once `field` is edited: its old message no longer describes what's typed. */
export function clearError(errors: FormErrors, field: keyof BookingForm): FormErrors {
  const rest = { ...errors };
  delete rest[field];
  return rest;
}

const KEY = "harbor-bookings";

export function loadBookings(): Booking[] {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]") as Booking[];
  } catch {
    return [];
  }
}

export function saveBooking(booking: Booking): void {
  localStorage.setItem(KEY, JSON.stringify([...loadBookings(), booking]));
}
