let product = [];

let total = 0;
let prices = [];


function addToCart(name, price) {
    alert(name + " added to cart for ₹" + price);
    product.push(name);
    prices.push(price);
    total += price;
    let cartItems = document.getElementById("cart-items");
    let totalAmount = document.getElementById("cart-total");
    cartItems.style.color = "yellow ";

    cartItems.innerHTML +=   name + " - ₹" +  price + "<br>";
    totalAmount.textContent = "₹" + total;

}


function checkout() {
    if (product.length === 0) {
        alert("Your cart is empty. Please add items before proceeding to checkout.");
        return;
    }
    else {

        alert("Congratulations! Your order has been placed successfully. " + "\n\nOrdered Items:\n" + product.map((item, index) => item + " - ₹" + prices[index]).join("\n") + "\n\nThank you for ordering from The Modern Cafe❤️!");

    }
    let cartItems = document.getElementById("cart-items");
    let totalAmount = document.getElementById("cart-total");
    cartItems.innerHTML = "";
    totalAmount.textContent = "₹0";
    product = [];
    prices = [];
    total = 0;
}

function clearCart() {
    let cartItems = document.getElementById("cart-items");
    let totalAmount = document.getElementById("cart-total");
    cartItems.innerHTML = "";
    totalAmount.textContent = "₹0";
    product = [];
    prices = [];
    total = 0;
    alert("Cart cleared successfully!");
}


