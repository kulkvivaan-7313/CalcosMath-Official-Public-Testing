
async function calculate() {
    const number = document.getElementById("number").value;

    if (number === "") {
        document.getElementById("result").textContent = "Please enter a number.";
        return;
    }

    const response = await fetch(`/api/square/${encodeURIComponent(number)}`);
    const data = await response.json();

    document.getElementById("result").textContent =
        data.error ?? `Answer: ${data.result}`;
}

async function calculateArithmetic() {
    const a = document.getElementById("first").value;
    const b = document.getElementById("second").value;
    const operation = document.getElementById("operation").value;

    if (a === "" || b === "") {
        document.getElementById("arithmeticResult").textContent =
            "Please enter both numbers.";
        return;
    }

    const response = await fetch(
        `/api/arithmetic/${operation}/${encodeURIComponent(Number(a))}/${encodeURIComponent(Number(b))}`
    );
    const data = await response.json();

    document.getElementById("arithmeticResult").textContent =
        data.error ?? `Answer: ${data.result}`;
}

async function solveAlgebra(operation, outputType = "text") {
    const equation = document.getElementById("equation").value;
    const resultBox = document.getElementById("result");

    if (!equation.trim()) {
        resultBox.textContent = "Please enter an expression or equation.";
        return;
    }

    resultBox.textContent = "Calculating...";

    try {
        const response = await fetch("/api/algebra", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                equation: equation,
                how_calculate: operation,
                how_product: outputType
            })
        });

        const data = await response.json();

        if (!response.ok) {
            resultBox.textContent = data.error || "Calculation failed.";
            return;
        }

        resultBox.textContent = String(data.result ?? "No result returned.");

    } catch (error) {
        resultBox.textContent = "Unable to connect to the calculator.";
        console.error(error);
    }
}
