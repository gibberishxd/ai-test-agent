import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router";
import { usePageTitle } from "../App";
import {
  clearError,
  nights,
  saveBooking,
  stayTotal,
  validate,
  type BookingForm,
  type FormErrors,
} from "../booking";
import { bug } from "../bugs";
import { formatMoney, ROOMS } from "../rooms";

const EMPTY: BookingForm = { guest: "", email: "", checkIn: "", checkOut: "" };

export function RoomPage() {
  const { id } = useParams();
  const room = ROOMS.find((r) => String(r.id) === id);
  usePageTitle(room?.name ?? "Room not found");
  const [availability, setAvailability] = useState("Checking availability…");
  const [form, setForm] = useState<BookingForm>(EMPTY);
  const [errors, setErrors] = useState<FormErrors>({});
  const [booked, setBooked] = useState(false);
  const saving = useRef(false);

  useEffect(() => {
    fetch("/api/availability?room=" + id)
      .then((response) => (response.ok ? response.json() : Promise.reject(response.status)))
      .then((data: { openFrom: string; openTo: string }) =>
        setAvailability("Open from " + data.openFrom + " to " + data.openTo),
      )
      .catch(() => setAvailability("Availability unknown"));
  }, [id]);

  if (!room) return <h1>Room not found</h1>;

  const nightCount = nights(form.checkIn, form.checkOut);
  const total = stayTotal(room.rate, nightCount);
  const set = (field: keyof BookingForm) => (event: { target: { value: string } }) => {
    setForm({ ...form, [field]: event.target.value });
    setErrors(clearError(errors, field));
  };

  function submit(event: FormEvent) {
    event.preventDefault();
    // Bug 5: no guard against a second submit while the first is being saved.
    if (!bug(5) && saving.current) return;
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    saving.current = true;
    saveBooking({ id: crypto.randomUUID(), roomId: room!.id, ...form, total });
    setBooked(true);
  }

  return (
    <article className="room">
      {/* Bug 6: the title never wraps, so a long room name runs off a phone screen. */}
      <h1 className="room-title" style={bug(6) ? { whiteSpace: "nowrap" } : undefined}>
        {room.name}
      </h1>
      <p>{room.summary}</p>
      <p className="muted">
        Sleeps {room.sleeps} · {formatMoney(room.rate)} per night · {availability}
      </p>

      <form className="form" onSubmit={submit} noValidate>
        <h2>Book this room</h2>
        <Field label="Guest name" id="guest" error={errors.guest}>
          <input id="guest" value={form.guest} onChange={set("guest")} />
        </Field>
        <Field label="Email" id="email" error={errors.email}>
          <input id="email" type="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Check-in" id="check-in" error={errors.checkIn}>
          <input id="check-in" type="date" value={form.checkIn} onChange={set("checkIn")} />
        </Field>
        <Field label="Check-out" id="check-out" error={errors.checkOut}>
          <input id="check-out" type="date" value={form.checkOut} onChange={set("checkOut")} />
        </Field>
        {bug(2) ? (
          // Bug 2: the caption isn't connected to the input, so the field has no name.
          <div className="field">
            <span>Phone (optional)</span>
            <input name="phone" type="tel" />
          </div>
        ) : (
          <Field label="Phone (optional)" id="phone">
            <input id="phone" name="phone" type="tel" />
          </Field>
        )}

        <p className="summary">
          {Math.max(nightCount, 0)} nights × {formatMoney(room.rate)}
          <br />
          Total: <strong data-testid="total">{formatMoney(total)}</strong>
        </p>
        <button type="submit" className="button" disabled={!bug(5) && booked}>
          Book now
        </button>
        {booked && (
          <p role="status">
            Booked! See <Link to="/bookings">My bookings</Link>.
          </p>
        )}
      </form>
    </article>
  );
}

function Field(props: { label: string; id: string; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={props.id}>{props.label}</label>
      {props.children}
      {props.error && <p className="field-error">{props.error}</p>}
    </div>
  );
}
