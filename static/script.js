
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


// CM-84 Account Signup

const signupForm = document.getElementById("signupForm");

function showVerificationForm(email) {
    const form = document.getElementById("verificationForm");
    form.dataset.email = email;
    form.hidden = false;
}

if (signupForm) {
    signupForm.addEventListener("submit", async function(event) {
        event.preventDefault();

        const resultElement = document.getElementById("signupResult");

        resultElement.textContent = "Creating your account...";

        try {
            const response = await fetch("/signup", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    username: document.getElementById("username").value,
                    email: document.getElementById("email").value,
                    password: document.getElementById("password").value
                })
            });

            const data = await response.json();

            resultElement.textContent =
                data.message || data.error || "Something went wrong.";

            if (response.ok || data.account_created) {
                showVerificationForm(document.getElementById("email").value);
                if (response.ok) {
                    document.getElementById("verificationCode").focus();
                }
            }

        } catch (error) {
            resultElement.textContent =
                "Signup could not be completed. Check your connection and try again.";
        }
    });
}

const verificationForm = document.getElementById("verificationForm");

if (verificationForm) {
    verificationForm.addEventListener("submit", async function(event) {
        event.preventDefault();

        const resultElement = document.getElementById("verificationResult");
        resultElement.textContent = "Verifying your email...";

        try {
            const response = await fetch("/verify-email", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    email: verificationForm.dataset.email,
                    code: document.getElementById("verificationCode").value
                })
            });

            const data = await response.json();
            resultElement.textContent =
                data.message || data.error || "Something went wrong.";
        } catch (error) {
            resultElement.textContent =
                "Email verification could not be completed. Check your connection and try again.";
        }
    });
}

const resendVerificationButton = document.getElementById("resendVerificationButton");

if (resendVerificationButton && verificationForm) {
    resendVerificationButton.addEventListener("click", async function() {
        const resultElement = document.getElementById("verificationResult");
        resultElement.textContent = "Requesting a new verification code...";

        try {
            const response = await fetch("/resend-verification", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    email: verificationForm.dataset.email
                })
            });

            const data = await response.json();
            resultElement.textContent =
                data.message || data.error || "Something went wrong.";
        } catch (error) {
            resultElement.textContent =
                "A new code could not be requested. Check your connection and try again.";
        }
    });
}
