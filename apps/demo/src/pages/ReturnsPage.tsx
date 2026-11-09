import { usePageTitle } from "../usePageTitle";

export function ReturnsPage() {
  usePageTitle("Returns policy");
  return (
    <>
      <h1>Returns policy</h1>
      <p>Return any unused item within 30 days for a full refund. (This is a demo shop.)</p>
    </>
  );
}
