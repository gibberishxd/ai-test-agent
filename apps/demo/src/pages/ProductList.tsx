import { useEffect, useState } from "react";
import { Link } from "react-router";
import { bug } from "../bugs";
import { formatPrice, PRODUCTS } from "../products";
import { usePageTitle } from "../usePageTitle";

export function ProductList() {
  usePageTitle("Shop");
  const [query, setQuery] = useState("");

  useEffect(() => {
    const onSearch = (event: Event) => setQuery((event as CustomEvent<string>).detail);
    document.addEventListener("demo-search", onSearch);
    return () => document.removeEventListener("demo-search", onSearch);
  }, []);

  const shown = PRODUCTS.filter((p) => p.name.toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <h1>Shop</h1>
      <p className="muted">Everyday things, made to last.</p>
      <ul className="grid">
        {shown.map((product) => (
          <li key={product.id} className="card">
            {/* Bug 4 (part 1): one product image has no alt text. */}
            <img
              src={product.image}
              alt={bug(4) && product.id === 4 ? undefined : product.name}
              width={240}
              height={200}
            />
            <h2 className="card-title">
              <Link to={`/products/${product.id}`}>{product.name}</Link>
            </h2>
            <p className="price">{formatPrice(product.price)}</p>
          </li>
        ))}
      </ul>
      {shown.length === 0 && <p>No products match “{query}”.</p>}
    </>
  );
}
