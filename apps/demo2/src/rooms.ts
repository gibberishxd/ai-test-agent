export type Room = { id: number; name: string; rate: number; sleeps: number; summary: string };

export const ROOMS: Room[] = [
  { id: 1, name: "Garden Room", rate: 120, sleeps: 2, summary: "Quiet, looks onto the garden." },
  { id: 2, name: "Loft", rate: 160, sleeps: 3, summary: "Top floor, with a reading corner." },
  {
    id: 3,
    name: "Harbourview-Panorama-Suite-with-Private-Terrace",
    rate: 240,
    sleeps: 4,
    summary: "Our largest room, with a terrace over the water.",
  },
];

export function formatMoney(amount: number): string {
  return "$" + amount.toFixed(2);
}
