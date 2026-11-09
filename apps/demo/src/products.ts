import { bug } from "./bugs";

export type Product = {
  id: number;
  name: string;
  price: number;
  description: string;
  image: string;
  /** Only some products have tracking metadata; bug 1 forgets that. */
  tracking?: { category: string };
};

export const PRODUCTS: Product[] = [
  {
    id: 1,
    name: "Ceramic Mug",
    price: 12,
    description: "A 350 ml stoneware mug with a matte glaze. Dishwasher safe.",
    image: "/products/1.svg",
    tracking: { category: "kitchen" },
  },
  {
    id: 2,
    name: "Linen Notebook",
    price: 8,
    description: "A5 notebook, 120 dotted pages, lay-flat binding.",
    image: "/products/2.svg",
    tracking: { category: "stationery" },
  },
  {
    id: 3,
    name: "Desk Lamp",
    price: 45,
    description: "Adjustable LED lamp with three brightness levels and a USB-C port.",
    image: "/products/3.svg",
    // No tracking metadata for this product.
  },
  {
    id: 4,
    name: "Canvas Tote",
    price: 18,
    description: "Heavy cotton canvas tote with an inside pocket.",
    image: "/products/4.svg",
    tracking: { category: "bags" },
  },
  {
    id: 5,
    name: "Wool Socks",
    // Bug 9: the price was imported with a decimal comma, which Number() can't parse.
    price: bug(9) ? Number("24,99") : 24.99,
    description: "Merino wool blend, reinforced heel and toe. One size.",
    image: "/products/5.svg",
    tracking: { category: "clothing" },
  },
  {
    id: 6,
    name: "Extra-Long Organic Cotton Weekend Travel Duffel Bag",
    price: 89,
    description: "Roomy enough for three days away, with a padded shoulder strap.",
    image: "/products/6.svg",
    tracking: { category: "bags" },
  },
];

export function findProduct(id: number): Product | undefined {
  return PRODUCTS.find((p) => p.id === id);
}

export function formatPrice(value: number): string {
  return `$${value.toFixed(2)}`;
}
