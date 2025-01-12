from flask import Flask, jsonify, request, render_template, session
from xumm import XummSdk
from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountInfo, AccountLines
from xrpl.models.transactions import OfferCreate
# from xrpl.transaction.main import safe_sign_and_autofill_transaction  # Remove this line

from xrpl.wallet import Wallet
import logging
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"


# Set up logging
logging.basicConfig(level=logging.DEBUG)

# XUMM API credentials
XUMM_API_KEY = os.environ.get("XUMM_API_KEY")
XUMM_API_SECRET = os.environ.get("XUMM_API_SECRET")

if not XUMM_API_KEY or not XUMM_API_SECRET:
    raise ValueError(
        "XUMM_API_KEY and XUMM_API_SECRET environment variables must be set."
    )

# Initialize the XUMM SDK with environment-provided credentials
xumm = XummSdk(XUMM_API_KEY, XUMM_API_SECRET)


# XRPL client
xrpl_client = JsonRpcClient("https://s1.ripple.com:51234/")

@app.route("/")
def index():
    """Render the homepage."""
    wallet_address = session.get("wallet_address")
    return render_template("index.html", wallet_address=wallet_address)

@app.route("/xumm/connect")
def xumm_connect():
    """
    Create a XUMM payload to allow the user to connect their wallet.
    This is effectively a SignIn transaction.
    """
    try:
        payload = xumm.payload.create({
            "txjson": {
                "TransactionType": "SignIn"
            }
        })
        session["uuid"] = payload.uuid  # Store the payload UUID in session
        return jsonify({"uuid": payload.uuid, "next": payload.next.always})
    except Exception as e:
        logging.error(f"Error creating XUMM payload: {e}")
        return jsonify({"error": "Error creating XUMM payload"}), 500

@app.route("/xumm/status")
def xumm_status():
    """
    Check the status of the XUMM SignIn payload to see if the user has signed in.
    """
    uuid = session.get("uuid")
    if not uuid:
        return jsonify({"connected": False, "wallet_address": None})

    try:
        payload_status = xumm.payload.get(uuid)
        if payload_status.meta.signed:
            # User has signed the payload
            session["wallet_address"] = payload_status.response.account
            return jsonify({"connected": True, "wallet_address": payload_status.response.account})
        else:
            return jsonify({"connected": False, "wallet_address": None})
    except Exception as e:
        logging.error(f"Error checking XUMM status: {e}")
        return jsonify({"error": "Error checking XUMM status"}), 500

@app.route("/api/balance")
def get_balance():
    """
    Retrieve the XRP balance for the connected wallet.
    """
    wallet_address = session.get("wallet_address")
    if not wallet_address:
        return jsonify({"error": "Wallet not connected"}), 400

    try:
        response = xrpl_client.request(AccountInfo(account=wallet_address))
        balance = int(response.result["account_data"]["Balance"]) / 1_000_000
        return jsonify({"wallet_address": wallet_address, "balance": balance})
    except Exception as e:
        logging.error(f"Error fetching balance: {e}")
        return jsonify({"error": "Failed to fetch balance"}), 500

@app.route("/api/token_search", methods=["GET"])
def token_search():
    """
    Search for a specific token (currency) on an issuer's account lines.
    """
    issuer = request.args.get("issuer")
    currency = request.args.get("currency")

    if not issuer or not currency:
        return jsonify({"error": "Issuer and currency are required"}), 400

    try:
        account_lines_req = AccountLines(account=issuer)
        response = xrpl_client.request(account_lines_req)

        if response.is_successful():
            tokens = [
                line for line in response.result["lines"]
                if line["currency"] == currency
            ]
            if tokens:
                return jsonify(tokens)
            else:
                return jsonify({"message": "Token not found"}), 404
        else:
            return jsonify({"error": response.result}), 500
    except Exception as e:
        logging.error(f"Error fetching token details: {e}")
        return jsonify({"error": "Failed to fetch token details"}), 500
    
@app.route("/api/account_lines")
def get_account_lines():
    """Return a list of trustlines (tokens) for the connected wallet."""
    wallet_address = session.get("wallet_address")
    if not wallet_address:
        return jsonify({"error": "Wallet not connected"}), 400

    try:
        lines_req = AccountLines(account=wallet_address)
        response = xrpl_client.request(lines_req)
        if response.is_successful():
            lines = response.result["lines"]
            return jsonify({"tokens": lines})
        else:
            return jsonify({"error": response.result}), 500
    except Exception as e:
        logging.error(f"Error fetching account lines: {e}")
        return jsonify({"error": "Failed to fetch account lines"}), 500


@app.route("/xumm/logout", methods=["POST"])
def xumm_logout():
    try:
        session.clear()  # Clear all session data
        return jsonify({"message": "Logged out"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/add_trustline", methods=["POST"])
def add_trustline():
    """Create a XUMM payload to add a new trustline."""
    wallet_address = session.get("wallet_address")
    if not wallet_address:
        return jsonify({"error": "Wallet not connected"}), 400

    data = request.json
    issuer = data.get("issuer")
    currency = data.get("currency")
    limit = data.get("limit")

    if not issuer or not currency or not limit:
        return jsonify({"error": "Missing trustline parameters"}), 400

    # Create a trustline transaction (TrustSet)
    trustset_json = {
        "TransactionType": "TrustSet",
        "Account": wallet_address,
        "LimitAmount": {
            "currency": currency,
            "issuer": issuer,
            "value": limit
        }
    }

    try:
        # Create a XUMM payload to sign the TrustSet transaction
        payload = xumm.payload.create({"txjson": trustset_json})
        return jsonify({
            "next": payload.next.always,
            "message": "Trustline creation payload. Please sign in XUMM."
        })
    except Exception as e:
        logging.error(f"Error creating trustline payload: {e}")
        return jsonify({"error": "Failed to create trustline payload"}), 500

@app.route("/api/trade", methods=["POST"])
def create_trade():
    """
    Create a simple OfferCreate transaction for trading an issued token.
    This outlines the transaction creation & payload. 
    (Further improvements like pathfinding, best execution, etc. would be needed for production.)
    """
    data = request.json
    wallet_address = session.get("wallet_address")
    if not wallet_address:
        return jsonify({"error": "Wallet not connected"}), 400

    try:
        # Example: Sell 10 tokens of 'CURRENCY' from 'issuer' for some XRP price
        issuer = data.get("issuer")
        currency = data.get("currency")
        amount = data.get("amount")         # e.g. '10'
        price_in_drops = data.get("price")  # e.g. 10000000 (10 XRP in drops)
        
        # For demonstration, we set the TakerPays as price_in_drops in XRP
        # and TakerGets as the custom currency.

        tx_json = {
            "TransactionType": "OfferCreate",
            "Account": wallet_address,
            "TakerGets": {
                "currency": currency,
                "issuer": issuer,
                "value": amount
            },
            "TakerPays": str(price_in_drops)  # in drops of XRP
        }

        # Create the XUMM payload for the user to sign
        payload = xumm.payload.create({"txjson": tx_json})
        # Store the trade payload UUID so you can check status later if needed
        trade_uuid = payload.uuid

        return jsonify({
            "uuid": trade_uuid,
            "next": payload.next.always,
            "message": "OfferCreate transaction created. Please sign in XUMM."
        })
    except Exception as e:
        logging.error(f"Error creating trade: {e}")
        return jsonify({"error": "Failed to create trade"}), 500
    

@app.route("/page1_html")
def page1_html():
    # Serve the "page1.html" template as raw text
    return render_template("page1.html")

@app.route("/page2_html")
def page2_html():
    # Serve the "page2.html" template as raw text
    return render_template("page2.html")







if __name__ == "__main__":
    # In production, set debug=False and run behind a proper WSGI server
    app.run(debug=True)
