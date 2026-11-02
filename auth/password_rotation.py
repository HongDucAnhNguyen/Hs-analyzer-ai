"""
Password Rotation Script with Email Notification

This script:
1. Generates a new secure random password
2. Updates the .env file with the new hashed password
3. Sends the new password to specified email recipients

Schedule: Every Sunday at 6:00 PM Vietnam time (UTC+7) = 11:00 UTC
"""

import os
import re
import sys
import secrets
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Vietnam timezone (UTC+7)
VIETNAM_TZ = timezone(timedelta(hours=7))

import bcrypt
from dotenv import load_dotenv


# =============================================================================
# Configuration
# =============================================================================

# Load environment variables
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
load_dotenv(ENV_FILE)

# Email Configuration (required - no fallbacks)
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT") or "587")
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # Gmail App Password

# Sender and Recipients (comma-separated lists)
EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_RECIPIENTS: list[str] = [
    email.strip()
    for email in (os.getenv("EMAIL_RECIPIENTS") or "").split(",")
    if email.strip()
]
EMAIL_BCC_RECIPIENTS: list[str] = [
    email.strip()
    for email in (os.getenv("EMAIL_BCC_RECIPIENTS") or "").split(",")
    if email.strip()
]

# Auth Configuration (required - no fallback)
AUTH_USERNAME = os.getenv("AUTH_USERNAME")


# =============================================================================
# Password Generation
# =============================================================================

def generate_secure_password(length: int = 16) -> str:
    """
    Generate a secure random password.
    
    Password includes:
    - Uppercase letters
    - Lowercase letters
    - Digits
    - Special characters
    """
    # Define character sets
    lowercase = string.ascii_lowercase
    uppercase = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%^&*"
    
    # Ensure at least one character from each set
    password = [
        secrets.choice(lowercase),
        secrets.choice(uppercase),
        secrets.choice(digits),
        secrets.choice(special),
    ]
    
    # Fill the rest with random characters from all sets
    all_chars = lowercase + uppercase + digits + special
    password.extend(secrets.choice(all_chars) for _ in range(length - 4))
    
    # Shuffle the password
    password_list = list(password)
    secrets.SystemRandom().shuffle(password_list)
    
    return ''.join(password_list)


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


# =============================================================================
# Environment File Update
# =============================================================================

def _read_token_version_from_env(content: str) -> int:
    match = re.search(r'AUTH_TOKEN_VERSION=(.+?)(?:\n|$)', content)
    if not match:
        return 0
    try:
        return int(match.group(1).strip())
    except ValueError:
        return 0


def update_env_file(new_password_hash: str, new_token_version: int) -> bool:
    """
    Update AUTH_PASSWORD_HASH and AUTH_TOKEN_VERSION in .env file.
    
    Returns True if successful, False otherwise.
    """
    try:
        if not ENV_FILE.exists():
            print(f"Error: .env file not found at {ENV_FILE}")
            return False
        
        # Read current content
        content = ENV_FILE.read_text()
        
        # Update AUTH_PASSWORD_HASH
        if "AUTH_PASSWORD_HASH=" in content:
            new_content = re.sub(
                r'AUTH_PASSWORD_HASH=.*',
                f'AUTH_PASSWORD_HASH={new_password_hash}',
                content
            )
        else:
            new_content = content.rstrip() + f"\nAUTH_PASSWORD_HASH={new_password_hash}\n"

        # Update AUTH_TOKEN_VERSION
        if "AUTH_TOKEN_VERSION=" in new_content:
            new_content = re.sub(
                r'AUTH_TOKEN_VERSION=.*',
                f'AUTH_TOKEN_VERSION={new_token_version}',
                new_content
            )
        else:
            new_content = new_content.rstrip() + f"\nAUTH_TOKEN_VERSION={new_token_version}\n"
        
        # Write updated content
        ENV_FILE.write_text(new_content)
        print("✓ Updated .env file with new password hash")
        print(f"✓ Updated .env file with new auth token version: {new_token_version}")
        return True
        
    except Exception as e:
        print(f"✗ Error updating .env file: {e}")
        return False


# =============================================================================
# Email Notification
# =============================================================================

def create_email_html(username: str, new_password: str, timestamp: str) -> str:
    """Create HTML email body."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
            }}
            .content {{
                background: #f9f9f9;
                padding: 24px;
                border: 1px solid #ddd;
                border-radius: 8px;
            }}
            .section-title {{
                font-weight: bold;
                margin-top: 16px;
            }}
            .credential {{
                font-family: 'Courier New', monospace;
                background: #f0f0f0;
                padding: 6px 10px;
                border-radius: 4px;
                display: inline-block;
                word-break: break-all;
            }}
            .notes {{
                margin-top: 16px;
                padding-left: 18px;
            }}
        </style>
    </head>
    <body>
        <div class="content">
            <p>Dear Global Trade and Customs Team,</p>
            <p>The password for your Global Trade Innovation Tool has been automatically reset as part of our weekly security protocol.</p>

            <div class="section-title">New Login credentials</div>
            <p>Username: <span class="credential">{username}</span></p>
            <p>New Password: <span class="credential">{new_password}</span></p>

            <div class="section-title">Generated at:</div>
            <p>{timestamp}</p>

            <div class="section-title">Key Notes:</div>
            <ol class="notes">
                <li>Each password remains valid for a duration of one week. Upon being reset, the previous password will no longer be functional.</li>
                <li>Please notify your authorized users to ensure uniterrupted access.</li>
                <li>DO NOT share this password with unauthorized parties.</li>
            </ol>
        </div>
    </body>
    </html>
    """


def create_email_text(username: str, new_password: str, timestamp: str) -> str:
    """Create plain text email body."""
    return f"""
Dear Global Trade and Customs Team,

The password for your Global Trade Innovation Tool has been automatically reset as part of our weekly security protocol.

New Login credentials
Username: {username}
New Password: {new_password}

Generated at:
{timestamp}

Key Notes:
1. Each password remains valid for a duration of one week. Upon being reset, the previous password will no longer be functional.
2. Please notify your authorized users to ensure uniterrupted access.
3. DO NOT share this password with unauthorized parties.
    """


def send_email(
    recipients: list[str],
    bcc_recipients: list[str],
    subject: str,
    username: str,
    new_password: str,
    timestamp: str
) -> bool:
    """
    Send password notification email to a list of recipients.
    
    Args:
        recipients: List of email addresses to send notification to
        username: The auth username
        new_password: The new generated password
        timestamp: Timestamp string for the email
    
    Returns True if successful, False otherwise.
    """
    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = EMAIL_SENDER
        msg["To"] = ", ".join(recipients)
        if bcc_recipients:
            msg["Bcc"] = ", ".join(bcc_recipients)
        
        # Create both plain text and HTML versions
        text_content = create_email_text(username, new_password, timestamp)
        html_content = create_email_html(username, new_password, timestamp)
        
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        print(f"Connecting to SMTP server {SMTP_SERVER}:{SMTP_PORT}...")
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(EMAIL_SENDER, recipients + bcc_recipients, msg.as_string())
        
        print(f"✓ Email sent successfully to {len(recipients)} recipient(s):")
        for recipient in recipients:
            print(f"   • {recipient}")
        if bcc_recipients:
            print(f"✓ BCC sent to {len(bcc_recipients)} recipient(s):")
            for recipient in bcc_recipients:
                print(f"   • {recipient}")
        return True
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"✗ SMTP Authentication Error: {e}")
        print("  → Make sure you're using a Gmail App Password, not your regular password")
        print("  → Generate one at: https://myaccount.google.com/apppasswords")
        return False
    except Exception as e:
        print(f"✗ Error sending email: {e}")
        return False


# =============================================================================
# Main Execution
# =============================================================================

def validate_config() -> list[str]:
    """
    Validate required environment variables.
    
    Returns list of missing required variables.
    """
    missing = []
    
    required_vars = {
        "SMTP_SERVER": SMTP_SERVER,
        "SMTP_USERNAME": SMTP_USERNAME,
        "SMTP_PASSWORD": SMTP_PASSWORD,
        "EMAIL_SENDER": EMAIL_SENDER,
        "EMAIL_RECIPIENTS": EMAIL_RECIPIENTS,
        "AUTH_USERNAME": AUTH_USERNAME,
    }
    
    for var_name, var_value in required_vars.items():
        if not var_value:
            missing.append(var_name)
    
    return missing


def rotate_password() -> bool:
    """
    Main function to rotate password and send notification.
    
    Returns True if all steps successful, False otherwise.
    """
    print("=" * 60)
    print("🔐 HS Code API - Password Rotation Script")
    print("=" * 60)
    
    # Validate configuration
    print("\n[0/3] Validating configuration...")
    missing_vars = validate_config()
    if missing_vars:
        print("✗ Missing required environment variables:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\n  → Please set these variables in your .env file")
        return False
    print(f"✓ Configuration valid")
    print(f"   Recipients ({len(EMAIL_RECIPIENTS)}):")
    for recipient in EMAIL_RECIPIENTS:
        print(f"   • {recipient}")
    
    now_vn = datetime.now(VIETNAM_TZ)
    timestamp = now_vn.strftime("%Y-%m-%d %H:%M:%S (Vietnam Time)")
    subject_date = now_vn.strftime("%d.%m.%Y")
    email_subject = f"Global Trade and Customs - Innovation Tool - Password reset({subject_date})"
    
    # Step 1: Generate new password
    print("\n[1/3] Generating new secure password...")
    new_password = generate_secure_password(16)
    print(f"✓ Generated new password: {new_password[:4]}{'*' * 8}{new_password[-4:]}")
    
    # Step 2: Hash and update .env
    print("\n[2/3] Updating .env file...")
    password_hash = hash_password(new_password)
    current_content = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    current_version = _read_token_version_from_env(current_content)
    new_token_version = current_version + 1
    if not update_env_file(password_hash, new_token_version):
        print("✗ Failed to update .env file. Aborting.")
        return False
    
    # Step 3: Send email notification
    print("\n[3/3] Sending email notification...")
    if not send_email(
        EMAIL_RECIPIENTS,
        EMAIL_BCC_RECIPIENTS,
        email_subject,
        AUTH_USERNAME,
        new_password,
        timestamp,
    ):
        print("✗ Failed to send email notification.")
        print(f"\n📋 Manual notification required:")
        print(f"   Username: {AUTH_USERNAME}")
        print(f"   New Password: {new_password}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ Password rotation completed successfully!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = rotate_password()
    sys.exit(0 if success else 1)

