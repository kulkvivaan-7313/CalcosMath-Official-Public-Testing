
from flask import Flask, jsonify, render_template, request
from main import addition, subtraction, multiplication, division, square
from main import solve_algebra
import sqlite3
from accounts import create_user, create_verification_token, verify_email_token, get_user_by_email


from mailer import send_verification_email

app = Flask(__name__)

@app.route("/verify-email")
def verify_email():
    token = request.args.get("token")

    if not token:
        return "Missing verification token.", 400

    connection = sqlite3.connect("accounts.db")

    try:
        verified = verify_email_token(connection, token)
    finally:
        connection.close()

    if verified:
        return "Your email has been verified!"

    return "Invalid or expired verification link.", 400


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/algebra.html")
def algebra_page():
    return render_template("algebra.html")


@app.route("/api/square/<value>")
def square_api(value):
    try:
        number = float(value)
    except ValueError:
        return jsonify({"error": "Invalid number"}), 400

    return jsonify({"result": square(number)})


@app.route("/api/arithmetic/<operation>/<a>/<b>")
def arithmetic(operation, a, b):
    try:
        left = float(a)
        right = float(b)
    except ValueError:
        return jsonify({"error": "Both numbers must be numeric."}), 400

    if operation == "add":
        result = addition(left, right)
    elif operation == "subtract":
        result = subtraction(left, right)
    elif operation == "multiply":
        result = multiplication(left, right)
    elif operation == "divide":
        result = division(left, right)
    else:
        return jsonify({"error": "Unknown operation"}), 400

    return jsonify({"result": result})


@app.route("/api/algebra", methods=["POST"])
def algebra_api():
    data = request.get_json()

    how_calculate = data["how_calculate"]
    how_product = data["how_product"]
    equation = data["equation"]

    result = solve_algebra(how_calculate, how_product, equation)

    return jsonify({"result": result})

@app.route("/signup", methods=["POST"])
def signup():

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request"}), 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not all(isinstance(value, str) and value.strip()
               for value in (username, email, password)):
        return jsonify({"error": "All fields are required"}), 400

    if len(password) < 12:
        return jsonify({"error": "Password must be at least 12 characters"}), 400

    connection = sqlite3.connect("accounts.db")

    try:
        user_id = create_user(connection, username, email, password)
        verification_token = create_verification_token(connection, user_id)
        send_verification_email(email,verification_token)

    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409

    finally:
        connection.close()

    return jsonify({
        "message": "Account created. Email verification required.",
        "user_id": user_id
    }), 201


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request"}), 400

    email = data.get("email")

    if not isinstance(email, str) or not email.strip():
        return jsonify({"error": "Email is required"}), 400

    connection = sqlite3.connect("accounts.db")

    try:
        user = get_user_by_email(connection, email.strip())

        if user is None:
            return jsonify({"error": "Account not found"}), 404

        user_id = user[0]
        token = create_verification_token(connection, user_id)

    finally:
        connection.close()

    send_verification_email(email.strip(), token)

    return jsonify({"message": "Verification email sent"}), 200

if __name__ == "__main__":
    app.run()

