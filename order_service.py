"""Standalone entry point for the isolated order-fulfillment test service.
Start command: python order_service.py   (does not import the live bots)."""
import os
from flask import Flask, jsonify
import order_fulfillment as of

app = Flask(__name__)
os.environ.setdefault("ORDER_FULFILLMENT_ENABLED", "1")
of.register(app)


@app.route("/health")
def health():
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
