import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents

app = FastAPI(title="Shopping API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utilities
class ProductOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    price: float
    category: str
    image: Optional[str] = None
    in_stock: bool

    class Config:
        from_attributes = True


def serialize_product(doc) -> ProductOut:
    return ProductOut(
        id=str(doc.get("_id")),
        title=doc.get("title"),
        description=doc.get("description"),
        price=float(doc.get("price", 0)),
        category=doc.get("category", "General"),
        image=doc.get("image"),
        in_stock=bool(doc.get("in_stock", True)),
    )


@app.get("/")
def read_root():
    return {"message": "Shopping API is running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    return response


# Seed endpoint to add sample products if collection empty
@app.post("/seed")
def seed_products():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    count = db["product"].count_documents({})
    if count > 0:
        return {"message": "Products already seeded", "count": count}

    sample = [
        {"title": "Classic Tee", "description": "Soft cotton t-shirt", "price": 19.99, "category": "Apparel", "image": "https://images.unsplash.com/photo-1520975916090-3105956dac38?w=800", "in_stock": True},
        {"title": "Premium Hoodie", "description": "Cozy fleece hoodie", "price": 49.0, "category": "Apparel", "image": "https://images.unsplash.com/photo-1520975893454-9d06fbe92d08?w=800", "in_stock": True},
        {"title": "Travel Mug", "description": "Insulated stainless steel", "price": 24.5, "category": "Accessories", "image": "https://images.unsplash.com/photo-1509460913899-d6f0e55cf84b?w=800", "in_stock": True},
        {"title": "Leather Journal", "description": "Handmade, dotted pages", "price": 29.95, "category": "Stationery", "image": "https://images.unsplash.com/photo-1519681393784-d120267933ba?w=800", "in_stock": True}
    ]

    for p in sample:
        create_document("product", p)

    return {"message": "Seeded products", "count": len(sample)}


# Public endpoints
@app.get("/products", response_model=List[ProductOut])
def list_products():
    docs = get_documents("product")
    return [serialize_product(d) for d in docs]


class CartItem(BaseModel):
    product_id: str
    quantity: int


class OrderRequest(BaseModel):
    customer_name: str
    customer_email: str
    customer_address: str
    items: List[CartItem]


@app.post("/checkout")
def checkout(order: OrderRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Fetch products and compute totals
    product_ids = [ObjectId(i.product_id) for i in order.items]
    products = list(db["product"].find({"_id": {"$in": product_ids}}))
    price_map = {str(p["_id"]): float(p.get("price", 0)) for p in products}

    line_items = []
    subtotal = 0.0
    for item in order.items:
        price = price_map.get(item.product_id, 0)
        line_total = price * item.quantity
        subtotal += line_total
        prod = next((p for p in products if str(p["_id"]) == item.product_id), None)
        line_items.append({
            "product_id": item.product_id,
            "title": prod.get("title") if prod else "Unknown",
            "price": price,
            "quantity": item.quantity
        })

    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)

    # Save order
    order_doc = {
        "customer_name": order.customer_name,
        "customer_email": order.customer_email,
        "customer_address": order.customer_address,
        "items": line_items,
        "subtotal": round(subtotal, 2),
        "tax": tax,
        "total": total,
    }

    order_id = create_document("order", order_doc)

    return {"order_id": order_id, "subtotal": round(subtotal, 2), "tax": tax, "total": total}


# Schema exposure for admin tools
@app.get("/schema")
def get_schema():
    try:
        from schemas import User, Product, Order, OrderItem
        return {
            "user": User.model_json_schema(),
            "product": Product.model_json_schema(),
            "order": Order.model_json_schema(),
            "orderitem": OrderItem.model_json_schema(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
