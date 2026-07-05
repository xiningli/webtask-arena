"""Checkout form: a three-step wizard (contact -> shipping -> review) with
server-side validation. Tests form filling, multi-step navigation, and
recovery from validation errors."""

from __future__ import annotations

import re
from typing import Any

from ..seeding import CITIES, PRODUCTS, STREETS, person, rng

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ZIP_RE = re.compile(r"^\d{5}$")


def _norm(s: str) -> str:
    return " ".join(str(s).split()).lower()


class CheckoutForm:
    id = "checkout-form"
    title = "Checkout"
    template = "checkout_form.html"

    def generate(self, seed: int) -> dict[str, Any]:
        r = rng(self.id, seed)
        buyer = person(r)
        expected = {
            "name": buyer["name"],
            "email": buyer["email"],
            "street": f"{r.randrange(100, 9900)} {r.choice(STREETS)}",
            "city": r.choice(CITIES),
            "zip": f"{r.randrange(10000, 99999)}",
        }
        return {
            "expected": expected,
            "product": r.choice(PRODUCTS),
            "contact": None,   # accepted step-1 data
            "shipping": None,  # accepted step-2 data
            "submitted": False,
        }

    def instruction(self, state: dict[str, Any]) -> str:
        e = state["expected"]
        return (
            f"Complete the checkout for {e['name']} (email: {e['email']}). "
            f"Ship to {e['street']}, {e['city']}, ZIP {e['zip']}. "
            "Submit the order at the review step."
        )

    def view(self, state: dict[str, Any]) -> dict[str, Any]:
        return {"product": state["product"]}

    def handle_action(self, state: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        op = payload.get("op")
        if op == "contact":
            errors = {}
            if not str(payload.get("name", "")).strip():
                errors["name"] = "Name is required."
            if not EMAIL_RE.match(str(payload.get("email", "")).strip()):
                errors["email"] = "Enter a valid email address."
            if errors:
                return {"ok": False, "errors": errors}
            state["contact"] = {
                "name": payload["name"].strip(),
                "email": payload["email"].strip(),
            }
            return {"ok": True}
        if op == "shipping":
            if state["contact"] is None:
                return {"ok": False, "errors": {"_": "Complete the contact step first."}}
            errors = {}
            for field, label in (("street", "Street address"), ("city", "City")):
                if not str(payload.get(field, "")).strip():
                    errors[field] = f"{label} is required."
            if not ZIP_RE.match(str(payload.get("zip", "")).strip()):
                errors["zip"] = "ZIP code must be exactly 5 digits."
            if errors:
                return {"ok": False, "errors": errors}
            state["shipping"] = {
                "street": payload["street"].strip(),
                "city": payload["city"].strip(),
                "zip": payload["zip"].strip(),
            }
            return {"ok": True}
        if op == "submit":
            if state["contact"] is None or state["shipping"] is None:
                return {"ok": False, "errors": {"_": "Earlier steps are incomplete."}}
            state["submitted"] = True
            return {"ok": True}
        return {"ok": False, "error": f"unknown op '{op}'"}

    def verify(self, state: dict[str, Any]) -> dict[str, bool]:
        exp = state["expected"]
        contact, shipping = state["contact"] or {}, state["shipping"] or {}
        return {
            "contact_correct": (
                _norm(contact.get("name", "")) == _norm(exp["name"])
                and _norm(contact.get("email", "")) == _norm(exp["email"])
            ),
            "shipping_correct": (
                _norm(shipping.get("street", "")) == _norm(exp["street"])
                and _norm(shipping.get("city", "")) == _norm(exp["city"])
                and shipping.get("zip", "").strip() == exp["zip"]
            ),
            "submitted": state["submitted"] is True,
        }
