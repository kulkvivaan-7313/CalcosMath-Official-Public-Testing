import logging
import os
import traceback
import resend


class VerificationEmailError(Exception):
    pass


def send_verification_email(email, token):
    api_key = os.getenv("RESEND_API_KEY")
    from_email = os.getenv("RESEND_FROM_EMAIL")

    if not api_key or not from_email:
        raise VerificationEmailError(
            "Email verification is not configured. Please try again later."
        )

    resend.api_key = api_key

    try:
        response = resend.Emails.send({
            "from": from_email,
            "to": [email],
            "subject": "Verify your CM-84 account",
            "text": (
                "Welcome to CM-84!\n\n"
                f"Your verification code is: {token}\n\n"
                "Enter this code on the signup page to verify your email. "
                "It expires in 15 minutes."
            )
        })
    except Exception as error:
        traceback_text = "".join(traceback.format_exception(error))
        for sensitive_value in (api_key, token, email):
            if sensitive_value:
                traceback_text = traceback_text.replace(
                    sensitive_value,
                    "[REDACTED]",
                )
        logging.error("Resend email delivery failed:\n%s", traceback_text)
        raise VerificationEmailError(
            "The verification email could not be sent. Please try again."
        ) from error

    response_id = (
        response.get("id")
        if isinstance(response, dict)
        else getattr(response, "id", None)
    )
    if not response_id:
        raise VerificationEmailError(
            "The verification email was not accepted for delivery."
        )

    return True