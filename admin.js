let csrfToken = "";
let currentProducts = [];

const byId = (id) => document.getElementById(id);
const money = (value) => `₹${Number(value).toLocaleString("en-IN")}`;

function showNotice(message, isError) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.className = isError ? "alert alert-danger" : "alert alert-success";
  if (!message) notice.className = "";
}

async function request(url, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body) headers["Content-Type"] = "application/json";
  if (options.method && options.method !== "GET" && csrfToken) headers["X-CSRF-Token"] = csrfToken;
  const response = await fetch(url, { ...options, headers, credentials: "same-origin" });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The request failed.");
  return result;
}

function setAuthenticated(authenticated) {
  byId("login-panel").classList.toggle("d-none", authenticated);
  byId("dashboard").classList.toggle("d-none", !authenticated);
  byId("logout-button").classList.toggle("d-none", !authenticated);
}

byId("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await request("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ password: byId("admin-password").value })
    });
    csrfToken = result.csrfToken;
    byId("login-form").reset();
    setAuthenticated(true);
    showNotice("Signed in successfully.", false);
    await loadDashboard();
  } catch (error) {
    showNotice(error.message, true);
  }
});

byId("logout-button").addEventListener("click", async () => {
  try {
    await request("/api/admin/logout", { method: "POST", body: "{}" });
    csrfToken = "";
    setAuthenticated(false);
    showNotice("Signed out.", false);
  } catch (error) {
    showNotice(error.message, true);
  }
});

function renderMetric(label, value) {
  const column = document.createElement("div");
  column.className = "col-6 col-lg";
  const panel = document.createElement("div");
  panel.className = "panel h-100";
  const heading = document.createElement("div");
  heading.className = "small text-light";
  heading.textContent = label;
  const amount = document.createElement("div");
  amount.className = "h3 text-cafe mb-0";
  amount.textContent = value;
  panel.append(heading, amount);
  column.append(panel);
  return column;
}

function renderOrders(orders) {
  const body = byId("orders-table");
  body.replaceChildren();
  orders.forEach((order) => {
    const row = document.createElement("tr");
    const ref = document.createElement("td");
    ref.textContent = order.order_number;
    const customer = document.createElement("td");
    customer.textContent = `${order.customer_name}\n${order.customer_phone}`;
    const total = document.createElement("td");
    total.textContent = money(order.total);
    const statusCell = document.createElement("td");
    const status = document.createElement("select");
    status.className = "form-select form-select-sm";
    status.setAttribute("aria-label", `Status for ${order.order_number}`);
    ["pending", "confirmed", "preparing", "ready", "completed", "cancelled"].forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      option.selected = order.status === value;
      status.append(option);
    });
    status.addEventListener("change", async () => {
      try {
        await request(`/api/admin/orders/${order.id}`, {
          method: "PUT",
          body: JSON.stringify({ status: status.value })
        });
        showNotice(`Order ${order.order_number} updated.`, false);
        await loadDashboard();
      } catch (error) {
        showNotice(error.message, true);
        await loadDashboard();
      }
    });
    statusCell.append(status);
    row.append(ref, customer, total, statusCell);
    body.append(row);
  });
  if (!orders.length) {
    const row = document.createElement("tr");
    const empty = document.createElement("td");
    empty.colSpan = 4;
    empty.textContent = "No orders yet.";
    row.append(empty);
    body.append(row);
  }
}

function renderProducts(products) {
  currentProducts = products;
  const body = byId("products-table");
  body.replaceChildren();
  products.forEach((product) => {
    const row = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = product.name + (product.available ? "" : " (inactive)");
    const price = document.createElement("td");
    price.textContent = money(product.price);
    const stock = document.createElement("td");
    stock.textContent = String(product.stock_quantity);
    const actions = document.createElement("td");
    const edit = document.createElement("button");
    edit.type = "button";
    edit.className = "btn btn-sm btn-outline-light me-1";
    edit.textContent = "Edit";
    edit.addEventListener("click", () => editProduct(product));
    actions.append(edit);
    if (product.available) {
      const archive = document.createElement("button");
      archive.type = "button";
      archive.className = "btn btn-sm btn-outline-warning";
      archive.textContent = "Archive";
      archive.addEventListener("click", () => archiveProduct(product));
      actions.append(archive);
    }
    row.append(name, price, stock, actions);
    body.append(row);
  });
}

async function loadDashboard() {
  try {
    const data = await request("/api/admin/dashboard");
    const metrics = byId("metrics");
    metrics.replaceChildren(
      renderMetric("Total orders", data.metrics.total_orders),
      renderMetric("Pending orders", data.metrics.pending_orders),
      renderMetric("Revenue", money(data.metrics.total_revenue)),
      renderMetric("Products", data.metrics.product_count),
      renderMetric("Low stock", data.metrics.low_stock)
    );
    renderOrders(data.orders);
    renderProducts(data.products);
  } catch (error) {
    showNotice(error.message, true);
    if (/login required/i.test(error.message)) setAuthenticated(false);
  }
}

function editProduct(product) {
  byId("product-id").value = String(product.id);
  byId("product-name").value = product.name;
  byId("product-description").value = product.description;
  byId("product-price").value = String(product.price);
  byId("product-stock").value = String(product.stock_quantity);
  byId("product-category").value = product.category;
  byId("product-image").value = product.image;
  byId("product-available").checked = product.available;
  byId("product-name").focus();
}

function resetProductForm() {
  byId("product-form").reset();
  byId("product-id").value = "";
  byId("product-image").value = "img/espresso.png";
  byId("product-available").checked = true;
}

byId("cancel-edit").addEventListener("click", resetProductForm);

byId("product-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = byId("product-id").value;
  const product = {
    name: byId("product-name").value,
    description: byId("product-description").value,
    price: Number(byId("product-price").value),
    stock_quantity: Number(byId("product-stock").value),
    category: byId("product-category").value,
    image: byId("product-image").value,
    available: byId("product-available").checked
  };
  try {
    await request(id ? `/api/admin/products/${id}` : "/api/admin/products", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(product)
    });
    resetProductForm();
    showNotice("Product saved.", false);
    await loadDashboard();
  } catch (error) {
    showNotice(error.message, true);
  }
});

async function archiveProduct(product) {
  if (!window.confirm(`Archive ${product.name}?`)) return;
  try {
    await request(`/api/admin/products/${product.id}`, { method: "DELETE" });
    showNotice("Product archived.", false);
    await loadDashboard();
  } catch (error) {
    showNotice(error.message, true);
  }
}
