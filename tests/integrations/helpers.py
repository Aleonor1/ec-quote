"""Date comune pentru testele de integrari."""
from __future__ import annotations

import json
from decimal import Decimal

import httpx

from ec_quote.contracts import Contact, LineChoices, LineProperty, PriceQuote

PRODUCT_GID = "gid://shopify/Product/15382742597956"
PERMANENT_VARIANT = "gid://shopify/ProductVariant/56069440405828"
DRAFT_GID = "gid://shopify/DraftOrder/991"
INVOICE_URL = "https://etichetecreative.ro/invoices/abc"


def make_quote(total: str = "217.00", product_id: str = PRODUCT_GID) -> PriceQuote:
    choices = LineChoices(
        product_id=product_id, material_name="Sticker Premium", shape="custom",
        width_cm=Decimal("6"), height_cm=Decimal("6"), quantity=100,
    )
    return PriceQuote(
        choices=choices, total=Decimal(total), total_ex_vat=Decimal("179.34"),
        unit_price=Decimal("2.17"), discount_percent=Decimal("0"), breakdown={},
        properties=[
            LineProperty(name="_Sticker Quantity", value="100"),
            LineProperty(name="Forma Taiere", value="custom"),
            LineProperty(name="Dimensiune", value="6 x 6 CM"),
            LineProperty(name="_calculator_price", value="217"),
            LineProperty(name="_product_gid", value=PRODUCT_GID),
            LineProperty(name="_Quantity", value="100"),
        ],
    )


def make_contact(**overrides) -> Contact:
    data = dict(channel="whatsapp", key="40722123456", phone="+40722123456",
                name="Ana", email=None, ad_source="meta ads, vara")
    data.update(overrides)
    return Contact(**data)


def body_of(request: httpx.Request) -> dict:
    return json.loads(request.content.decode("utf-8"))


class Recorder:
    """Transport fals: raspunde din coada si pastreaza cererile."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request)
        return item

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))
