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

export function validate(form: BookingForm): FormErrors {
  const errors: FormErrors = {};
  if (!form.guest.trim()) errors.guest = "Enter the guest's name.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errors.email = "Enter a valid email address.";
  if (!form.checkIn) errors.checkIn = "Choose a check-in date.";
  if (!form.checkOut) errors.checkOut = "Choose a check-out date.";
  // Bug 4: a check-out before check-in is let through.
  else if (!bug(4) && nights(form.checkIn, form.checkOut) <= 0) {
    errors.checkOut = "Check-out must be after check-in.";
  }
  return errors;
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
