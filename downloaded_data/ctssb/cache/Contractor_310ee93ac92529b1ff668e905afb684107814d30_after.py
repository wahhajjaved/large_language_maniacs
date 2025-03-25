from flask import Flask, render_template, redirect, url_for, request
from pymongo import MongoClient
from bson.objectid import ObjectId
import os

app = Flask(__name__)

host = os.environ.get("MONGODB_URI", "mongodb://localhost:27017/my_app_db")
client = MongoClient(host=f"{host}?retryWrites=false")
db = client.get_default_database()
listings = db.listings
cart = db.cart


@app.route("/")
def listings_index():
    """Return homepage"""
    return render_template("listings_index.html", listings=listings.find())


@app.route("/cart")
def cart_show():
    """Show the user's cart"""
    total = 0
    for item in cart.find():
        total += int(item["price"])
    return render_template("cart_show.html", cart=cart.find())


@app.route("/cart/<item_id>")
def cart_item_show(item_id):
    """Show a single item in a user's cart"""
    item = cart.find_one({"_id": ObjectId(item_id)})
    return render_template("cart_item_show.html", item=item)


@app.route("/cart/<item_id>/delete", methods=["POST"])
def cart_delete(item_id):
    """Delete an item from the user's cart"""
    cart.delete_one({"_id": ObjectId(item_id)})
    return redirect(url_for("cart_show"))


@app.route("/cart/destroy")
def cart_destroy():
    """Delete all items in a user's cart"""
    for item in cart.find():
        cart.delete_one({"_id": ObjectId(item["_id"])})
    return redirect(url_for("cart_show"))


@app.route("/cart/checkout")
def cart_checkout():
    """Allow the user to checkout"""
    total = 0
    for item in cart.find():
        total += int(item["price"])
    return redirect(url_for("cart_destroy"))


@app.route("/listings/new")
def new_listing():
    """Return new listing creation page"""
    return render_template("listings_new.html", listing={},
                           title='New listing')


@app.route("/listings/new", methods=["POST"])
def listings_new():
    """Allow the user to create a new listing"""
    listing = {
        "name": request.form.get("name"),
        "price": request.form.get("price"),
        "image": request.form.get("image")
    }
    listing_id = listings.insert_one(listing).inserted_id
    return redirect(url_for("listings_show", listing_id=listing_id))


@app.route("/listings/<listing_id>")
def listings_show(listing_id):
    """Show a single listing."""
    listing = listings.find_one({"_id": ObjectId(listing_id)})
    return render_template("listings_show.html", listing=listing)


@app.route('/listings/<listing_id>', methods=['POST'])
def listings_update(listing_id):
    """Submit an edited listing."""
    updated_listing = {
        'title': request.form.get('title'),
        'price': request.form.get('price'),
        'image': request.form.get('image')
    }
    listings.update_one(
        {'_id': ObjectId(listing_id)},
        {'$set': updated_listing})
    return redirect(url_for('listings_show', listing_id=listing_id))


@app.route("/listings/<listing_id>/edit")
def listings_edit(listing_id):
    """Show the edit form for a listing."""
    listing = listings.find_one({"_id": ObjectId(listing_id)})
    return render_template("listings_edit.html", listing=listing,
                           title="Edit listing")


@app.route('/listings/<listing_id>/delete', methods=['POST'])
def listings_delete(listing_id):
    """Delete one listing."""
    listings.delete_one({'_id': ObjectId(listing_id)})
    return redirect(url_for('listings_index'))


@app.route('/listings/<listing_id>/add-to-cart', methods=['POST'])
def add_to_cart(listing_id):
    """Add an item to the user's cart"""
    item = listings.find_one({"_id": ObjectId(listing_id)})
    for _ in range(int(request.form.get("quant"))):
        new_item = {
            "name": item["name"],
            "price": item["price"],
            "image": item["image"]
        }
        cart.insert_one(new_item)
    return redirect(url_for('cart_show'))


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=os.environ.get('PORT', 5000))
