// Deep mode's test page script: a counter, a hover tip, and Enter in the search field.
let total = 0;
document.getElementById("add").onclick = () => {
  total += 1;
  document.getElementById("total").textContent = String(total);
};
document.getElementById("hover-me").onmouseenter = () => {
  document.getElementById("tip").hidden = false;
};
document.getElementById("q").onkeydown = (event) => {
  if (event.key === "Enter") {
    document.getElementById("searched").textContent = "Searched: " + event.target.value;
  }
};
console.warn("deep.js loaded");
