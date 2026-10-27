import os
import resend

def send_verification_email(email, token):
    resend.api_key = os.environ["RESEND_API_KEY"]

    base_url = os.environ["APP_BASE_URL"].rstrip("/")
    verification_link = f"{base_url}/verify-email?token={token}"

    result = resend.Emails.send({
        "from": "CM-84 <onboarding@resend.dev>",
        "to": [email],
        "subject": "Verify your CM-84 account",
        "text": (
            "Welcome to CM-84!\n\n"
            "Verify your email using this link:\n"
            f"{verification_link}\n\n"
            "This link expires in 15 minutes."
        )
    })

    print("Resend response:", result)
    return result