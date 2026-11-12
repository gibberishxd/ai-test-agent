import { useEffect, type ReactNode } from "react";
import { BrowserRouter, Link, Route, Routes } from "react-router";
import { BookingsPage } from "./pages/BookingsPage";
import { RoomList } from "./pages/RoomList";
import { RoomPage } from "./pages/RoomPage";

export function usePageTitle(title: string): void {
  useEffect(() => {
    document.title = title + " · Harbor Rooms";
  }, [title]);
}

function Layout({ children }: { children: ReactNode }) {
  return (
    <>
      <header className="header">
        <Link to="/" className="brand">
          Harbor Rooms
        </Link>
        <nav className="nav">
          <Link to="/">Rooms</Link>
          <Link to="/bookings">My bookings</Link>
        </nav>
      </header>
      <main className="main">{children}</main>
      <footer className="footer">Harbor Rooms · 4 Quay Street</footer>
    </>
  );
}

function NotFound() {
  usePageTitle("Not found");
  return <h1>Page not found</h1>;
}

export function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<RoomList />} />
          <Route path="/rooms/:id" element={<RoomPage />} />
          <Route path="/bookings" element={<BookingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
