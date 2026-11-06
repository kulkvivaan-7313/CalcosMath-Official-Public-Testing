
import os
import sqlite3
from datetime import timedelta

from flask import Flask, jsonify, render_template, request, session, url_for
from main import addition, subtraction, multiplication, division, square
from main import solve_algebra
import re
from accounts import (
    DATABASE_PATH,
    authenticate_user,
    confirm_pending_registration_delivery,
    create_pending_registration,
    create_verification_token,
    delete_pending_registration,
    get_user_by_email,
    initialize_database,
    resend_pending_verification,
    verify_pending_registration,
    verify_email_token,
)
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file




from mailer import VerificationEmailError, send_verification_email

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=os.getenv(
        "SESSION_COOKIE_SECURE",
        "true",
    ).strip().lower() in {"1", "true", "yes"},
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)
initialize_database()

@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if request.method == "POST":
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            data = request.form.to_dict()

        email = data.get("email")
        code = data.get("code")

        if not isinstance(email, str) or not email.strip():
            return jsonify({"error": "Email is required"}), 400

        if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
            return jsonify({"error": "Enter the 6-digit verification code"}), 400

        connection = sqlite3.connect(DATABASE_PATH)

        try:
            result = verify_pending_registration(
                connection,
                email.strip(),
                code,
            )
            if result == "not_found":
                verified = verify_email_token(connection, code, email.strip())
                result = "verified" if verified else "invalid"
        finally:
            connection.close()

        if result == "verified":
            return jsonify({
                "message": "Your account has been created successfully."
            })

        errors = {
            "invalid": "Invalid verification code",
            "expired": "Verification code expired. Request a new code.",
            "locked": "Too many incorrect attempts. Request a new code.",
            "delivery_pending": "Verification email delivery is not confirmed.",
        }
        status = 503 if result == "delivery_pending" else 400
        return jsonify({"error": errors[result]}), status

    token = request.args.get("token")

    if not token:
        return "Missing verification token.", 400

    connection = sqlite3.connect(DATABASE_PATH)

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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request"}), 400

    email = data.get("email")
    password = data.get("password")
    if (
        not isinstance(email, str)
        or not email.strip()
        or not isinstance(password, str)
        or not password
    ):
        return jsonify({"error": "Email and password are required"}), 400

    if not app.config.get("SECRET_KEY"):
        app.logger.error("Login unavailable because FLASK_SECRET_KEY is not configured.")
        return jsonify({"error": "Login is temporarily unavailable."}), 503

    connection = sqlite3.connect(DATABASE_PATH)
    try:
        user = authenticate_user(connection, email, password)
    finally:
        connection.close()

    if user is None:
        return jsonify({"error": "Invalid email or password"}), 401

    user_id, _username = user
    session.clear()
    session["user_id"] = user_id
    session.permanent = True

    return jsonify({
        "message": "Login successful",
        "redirect_url": url_for("home"),
    })


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

    if data is None:
        data = request.form.to_dict()

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request"}), 400

    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    if not all(isinstance(value, str) and value.strip()
               for value in (username, email, password)):
        return jsonify({"error": "All fields are required"}), 400

    username = username.strip()
    email = email.strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return jsonify({"error": "Enter a valid email address"}), 400

    if len(password) < 12:
        return jsonify({"error": "Password must be at least 12 characters"}), 400

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        pending_id, verification_code, generation = create_pending_registration(
            connection,
            username,
            email,
            password,
        )

    except sqlite3.IntegrityError:
        return jsonify({"error": "Username or email already exists"}), 409

    finally:
        connection.close()

    try:
        if not send_verification_email(email, verification_code):
            raise VerificationEmailError(
                "The verification email could not be accepted for delivery."
            )
    except VerificationEmailError as error:
        app.logger.warning("Signup verification email could not be sent.")
        connection = sqlite3.connect(DATABASE_PATH)
        try:
            delete_pending_registration(connection, pending_id, generation)
        finally:
            connection.close()
        return jsonify({
            "error": str(error),
        }), 503

    connection = sqlite3.connect(DATABASE_PATH)
    try:
        delivery_confirmed = confirm_pending_registration_delivery(
            connection,
            pending_id,
            generation,
        )
    finally:
        connection.close()

    if not delivery_confirmed:
        return jsonify({
            "error": "The verification registration changed during delivery. Request a new code."
        }), 503

    return jsonify({
        "message": "Verification email sent. Enter the code to create your account."
    }), 201


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid request"}), 400

    email = data.get("email")

    if not isinstance(email, str) or not email.strip():
        return jsonify({"error": "Email is required"}), 400

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        pending = resend_pending_verification(connection, email.strip())
        if pending is not None:
            pending_id, token, generation = pending
            pending_email = email.strip()
        else:
            user = get_user_by_email(connection, email.strip())

            if user is None:
                return jsonify({"error": "Account not found"}), 404

            user_id, email_verified = user
            if email_verified:
                return jsonify({"error": "This email is already verified"}), 409

            token = create_verification_token(connection, user_id)
            pending_id = None
            generation = None
            pending_email = email.strip()
    finally:
        connection.close()

    try:
        if not send_verification_email(pending_email, token):
            raise VerificationEmailError(
                "The verification email could not be accepted for delivery."
            )

        if pending_id is not None:
            connection = sqlite3.connect(DATABASE_PATH)
            try:
                if not confirm_pending_registration_delivery(
                    connection,
                    pending_id,
                    generation,
                ):
                    raise VerificationEmailError(
                        "The verification registration is no longer available."
                    )
            finally:
                connection.close()
    except VerificationEmailError as error:
        app.logger.warning("Resend verification email could not be sent.")
        return jsonify({"error": str(error)}), 503

    return jsonify({"message": "Verification email sent"}), 200

if __name__ == "__main__":
    app.run(port=5001)
