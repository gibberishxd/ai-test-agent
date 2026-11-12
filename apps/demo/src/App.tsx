import { BrowserRouter, Route, Routes } from "react-router";
import { Layout } from "./Layout";
import { CartPage } from "./pages/CartPage";
import { CheckoutPage } from "./pages/CheckoutPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFound } from "./pages/NotFound";
import { OrderPage, OrdersPage } from "./pages/OrdersPage";
import { ProductList } from "./pages/ProductList";
import { ProductPage } from "./pages/ProductPage";
import { ProfilePage } from "./pages/ProfilePage";
import { ReturnsPage } from "./pages/ReturnsPage";
import { StoreProvider } from "./store";

export function App() {
  return (
    <BrowserRouter>
      <StoreProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<ProductList />} />
            <Route path="/products/:id" element={<ProductPage />} />
            <Route path="/cart" element={<CartPage />} />
            <Route path="/checkout" element={<CheckoutPage />} />
            <Route path="/login" element={<LoginPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/orders" element={<OrdersPage />} />
            <Route path="/orders/:id" element={<OrderPage />} />
            <Route path="/returns" element={<ReturnsPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Layout>
      </StoreProvider>
    </BrowserRouter>
  );
}
