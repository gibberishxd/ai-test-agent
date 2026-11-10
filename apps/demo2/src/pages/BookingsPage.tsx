import { usePageTitle } from "../App";
import { loadBookings } from "../booking";
import { formatMoney, ROOMS } from "../rooms";

export function BookingsPage() {
  usePageTitle("My bookings");
  const bookings = loadBookings();
  return (
    <>
      <h1>My bookings</h1>
      {bookings.length === 0 ? (
        <p>No bookings yet.</p>
      ) : (
        <ul className="bookings" data-testid="bookings">
          {bookings.map((booking) => (
            <li key={booking.id}>
              <strong>{ROOMS.find((r) => r.id === booking.roomId)?.name ?? "Room"}</strong> for{" "}
              {booking.guest}, {booking.checkIn} to {booking.checkOut}, {formatMoney(booking.total)}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
