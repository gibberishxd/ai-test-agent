import { Link } from "react-router";
import { usePageTitle } from "../App";
import { formatMoney, ROOMS } from "../rooms";

export function RoomList() {
  usePageTitle("Rooms");
  return (
    <>
      <h1>Rooms</h1>
      <p className="muted">Small guesthouse by the harbour. Pick a room to book.</p>
      <ul className="grid">
        {ROOMS.map((room) => (
          <li key={room.id} className="card">
            <h2 className="card-title">
              <Link to={"/rooms/" + room.id}>{room.name}</Link>
            </h2>
            <p>{room.summary}</p>
            <p className="price">{formatMoney(room.rate)} per night</p>
          </li>
        ))}
      </ul>
    </>
  );
}
