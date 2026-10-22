const CART_KEY = "modernCafeCart";
const API_BASE = "/api";
let menuProducts = [];

function readCart() {
  try {
    const saved = JSON.parse(localStorage.getItem(CART_KEY) || "[]");
    return Array.isArray(saved) ? saved.filter((item) =>
      item && Number.isInteger(item.productId) && Number.isInteger(item.quantity) && item.quantity > 0
    ) : [];
  } catch (error) {
    console.error("Unable to read the saved cart.", error);
    return [];
  }
}

function saveCart(cart) {
  localStorage.setItem(CART_KEY, JSON.stringify(cart));
  renderCart();
}

function formatPrice(amount) {
  return `₹${Number(amount).toLocaleString("en-IN")}`;
}

async function loadProducts() {
  try {
    const response = await fetch(`${API_BASE}/products`);
    if (!response.ok) throw new Error("Menu is currently unavailable.");
    menuProducts = await response.json();
    const byName = new Map(menuProducts.map((item) => [item.name.toLowerCase(), item]));
    document.querySelectorAll("[data-menu-category]").forEach((container) => {
      const category = container.dataset.menuCategory;
      const visible = new Set(Array.from(container.querySelectorAll(".card-title"))
        .map((element) => element.textContent.trim().toLowerCase()));
      menuProducts.filter((product) => product.available && product.category === category && !visible.has(product.name.toLowerCase()))
        .forEach((product) => container.append(createProductCard(product)));
    });
    document.querySelectorAll(".menu-card").forEach((card) => {
      const nameElement = card.querySelector(".card-title");
      if (!nameElement) return;
      const product = byName.get(nameElement.textContent.trim().toLowerCase());
      if (!product) return;
      const categoryContainer = card.closest("[data-menu-category]");
      const column = card.parentElement;
      if (!product.available || (categoryContainer && product.category !== categoryContainer.dataset.menuCategory)) {
        if (column) column.hidden = true;
        return;
      }
      const priceElement = card.querySelector(".price");
      const button = card.querySelector("button[onclick^='addToCart']");
      if (priceElement) priceElement.textContent = formatPrice(product.price);
      if (button) {
        button.disabled = !product.available || product.stock_quantity <= 0;
        button.textContent = button.disabled ? "Unavailable" : "Add to Cart";
        button.dataset.productId = String(product.id);
      }
    });
    renderCart();
  } catch (error) {
    console.error(error);
    const message = document.getElementById("cart-message");
    if (message) {
      message.textContent = "Could not load the live menu. Please refresh or contact the cafe.";
      message.className = "text-danger mt-3";
    }
  }
}

function createProductCard(product) {
  const column = document.createElement("div");
  column.className = "col-md-6 col-lg-4";
  const card = document.createElement("div");
  card.className = "card menu-card h-100";
  const image = document.createElement("img");
  image.src = product.image;
  image.alt = product.name;
  image.className = "card-img-top";
  const body = document.createElement("div");
  body.className = "card-body text-center";
  const title = document.createElement("h5");
  title.className = "card-title text-warning fs-4";
  title.textContent = product.name;
  const description = document.createElement("p");
  description.className = "description";
  description.textContent = product.description;
  const price = document.createElement("p");
  price.className = "price mt-3";
  price.textContent = formatPrice(product.price);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn btn-cafe w-100 mt-3";
  button.textContent = product.available && product.stock_quantity > 0 ? "Add to Cart" : "Unavailable";
  button.disabled = !product.available || product.stock_quantity <= 0;
  button.addEventListener("click", () => addToCart(product.name, product.price));
  body.append(title, description, price, button);
  card.append(image, body);
  column.append(card);
  return column;
}

function addToCart(name, _displayPrice) {
  const product = menuProducts.find((item) => item.name.toLowerCase() === name.toLowerCase());
  if (!product || !product.available || product.stock_quantity <= 0) {
    alert("This item is currently unavailable.");
    return;
  }
  const cart = readCart();
  const line = cart.find((item) => item.productId === product.id);
  if (line) line.quantity += 1;
  else cart.push({ productId: product.id, quantity: 1 });
  saveCart(cart);
  alert(`${product.name} added to cart.`);
}

function renderCart() {
  const cartItems = document.getElementById("cart-items");
  const totalAmount = document.getElementById("cart-total");
  if (!cartItems || !totalAmount) return;
  const cart = readCart();
  let total = 0;
  cartItems.replaceChildren();

  cart.forEach((line) => {
    const product = menuProducts.find((item) => item.id === line.productId);
    if (!product) return;
    const row = document.createElement("div");
    row.className = "d-flex align-items-center justify-content-between gap-3 mb-3 flex-wrap";
    const label = document.createElement("span");
    label.textContent = `${product.name} — ${formatPrice(product.price)} each`;
    const controls = document.createElement("div");
    controls.className = "d-flex align-items-center gap-2";
    const quantity = document.createElement("input");
    quantity.type = "number";
    quantity.min = "1";
    quantity.max = "99";
    quantity.value = String(line.quantity);
    quantity.setAttribute("aria-label", `${product.name} quantity`);
    quantity.className = "form-control";
    quantity.style.width = "5rem";
    quantity.addEventListener("change", () => updateQuantity(product.id, quantity.value));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "btn btn-outline-light";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => removeFromCart(product.id));
    controls.append(quantity, remove);
    row.append(label, controls);
    cartItems.append(row);
    total += product.price * line.quantity;
  });

  totalAmount.textContent = formatPrice(total);
  const emptyMessage = document.getElementById("cart-empty");
  if (emptyMessage) emptyMessage.hidden = cart.length !== 0;
}

function updateQuantity(productId, value) {
  const quantity = Number.parseInt(value, 10);
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 99) {
    alert("Choose a quantity between 1 and 99.");
    renderCart();
    return;
  }
  const cart = readCart();
  const line = cart.find((item) => item.productId === productId);
  if (line) line.quantity = quantity;
  saveCart(cart);
}

function removeFromCart(productId) {
  saveCart(readCart().filter((item) => item.productId !== productId));
}

async function checkout() {
  const cart = readCart();
  if (!cart.length) {
    alert("Your cart is empty. Please add items before proceeding to checkout.");
    return;
  }
  const name = document.getElementById("customer-name")?.value.trim();
  const email = document.getElementById("customer-email")?.value.trim();
  const phone = document.getElementById("customer-phone")?.value.trim();
  if (!name || !email || !phone) {
    alert("Please enter your name, email, and phone number before placing the order.");
    document.getElementById("customer-name")?.focus();
    return;
  }
  const button = document.querySelector(".btn-checkout");
  if (button) button.disabled = true;
  try {
    const response = await fetch(`${API_BASE}/orders`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer: { name, email, phone },
        items: cart.map(({ productId, quantity }) => ({ productId, quantity }))
      })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Your order could not be placed.");
    localStorage.removeItem(CART_KEY);
    renderCart();
    document.getElementById("checkout-form")?.reset();
    alert(`Order ${result.orderNumber} placed successfully. Total: ${formatPrice(result.total)}. Thank you!`);
    await loadProducts();
  } catch (error) {
    alert(error.message);
  } finally {
    if (button) button.disabled = false;
  }
}

function clearCart() {
  saveCart([]);
  alert("Cart cleared successfully!");
}

document.addEventListener("DOMContentLoaded", loadProducts);
