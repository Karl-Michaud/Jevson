from pydantic import BaseModel


class Product(BaseModel):
    """Data model for a Amazon Product."""

    title: str
    category: str
    discount: str
    price: str
    rating: str
    review: str
    description: str
    inventory: str
