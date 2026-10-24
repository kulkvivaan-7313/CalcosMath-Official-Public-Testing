
from flask import Flask, jsonify, render_template, request
from main import addition, subtraction, multiplication, division, square
from main import solve_algebra

app = Flask(__name__)


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


if __name__ == "__main__":
    app.run()

