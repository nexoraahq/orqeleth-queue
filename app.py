from flask import Flask, render_template, request, jsonify, url_for, session, redirect
import sqlite3
import secrets
import string
import re
from pathlib import Path
import os
from dotenv import load_dotenv
import resend


# ============================================================
# ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")
load_dotenv()

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

# This must be a sender address on your verified Resend domain.
RESEND_FROM_EMAIL = os.getenv(
    "RESEND_FROM_EMAIL",
    "ORQELETH AI <noreply@joinorqeleth.com>"
)

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
else:
    print("WARNING: RESEND_API_KEY is missing.")


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "orqeleth-development-secret-change-this"
)


# ============================================================
# DATABASE
# ============================================================

DATABASE_DIR = BASE_DIR / "database"
DATABASE_DIR.mkdir(exist_ok=True)

DATABASE = DATABASE_DIR / "queue.db"


def get_db():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_database():

    connection = get_db()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id TEXT UNIQUE NOT NULL,

            name TEXT NOT NULL,

            email TEXT UNIQUE NOT NULL,

            username TEXT UNIQUE,

            referral_code TEXT UNIQUE NOT NULL,

            referred_by TEXT,

            is_verified INTEGER DEFAULT 0,

            verified_referrals INTEGER DEFAULT 0,

            queue_position INTEGER,

            verification_token TEXT,

            verification_expires TIMESTAMP,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_referral
        ON users(referral_code)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_verified
        ON users(is_verified)
    """)

    # --------------------------------------------------------
    # Upgrade older database versions
    # --------------------------------------------------------

    columns = connection.execute(
        "PRAGMA table_info(users)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    if "verification_token" not in column_names:

        connection.execute("""
            ALTER TABLE users
            ADD COLUMN verification_token TEXT
        """)

    if "verification_expires" not in column_names:

        connection.execute("""
            ALTER TABLE users
            ADD COLUMN verification_expires TIMESTAMP
        """)

    connection.commit()
    connection.close()


# ============================================================
# HELPERS
# ============================================================

def generate_user_id():

    return (
        "ORQ-"
        + secrets.token_hex(6).upper()
    )


def generate_code(length=8):

    characters = (
        string.ascii_uppercase
        + string.digits
    )

    while True:

        code = "".join(
            secrets.choice(characters)
            for _ in range(length)
        )

        connection = get_db()

        existing = connection.execute(
            """
            SELECT id
            FROM users
            WHERE referral_code = ?
            """,
            (code,)
        ).fetchone()

        connection.close()

        if existing is None:
            return code


def valid_email(email):

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    return (
        re.match(pattern, email)
        is not None
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    referral_code = request.args.get(
        "ref",
        ""
    ).strip().upper()

    if referral_code:

        connection = get_db()

        referrer = connection.execute(
            """
            SELECT id
            FROM users
            WHERE referral_code = ?
            AND is_verified = 1
            """,
            (referral_code,)
        ).fetchone()

        connection.close()

        if referrer:
            session["referral_code"] = referral_code

    return render_template(
        "index.html"
    )


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "service": "ORQELETH Queue"
    })


# ============================================================
# CAMPAIGN COUNT
# ============================================================

@app.route("/api/campaign")
def campaign():

    connection = get_db()

    result = connection.execute(
        """
        SELECT COUNT(*)
        FROM users
        WHERE is_verified = 1
        """
    ).fetchone()

    connection.close()

    verified_count = result[0]

    return jsonify({

        "verified_registrations":
            verified_count,

        "capacity":
            100000,

        "remaining":
            max(
                100000 - verified_count,
                0
            )
    })


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/api/register",
    methods=["POST"]
)
def register():

    # --------------------------------------------------------
    # READ REQUEST
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "Invalid request."
        }), 400


    # --------------------------------------------------------
    # GET DATA
    # --------------------------------------------------------

    name = str(
        data.get("name", "")
    ).strip()

    email = str(
        data.get("email", "")
    ).strip().lower()

    username = str(
        data.get("username", "")
    ).strip()

    referred_by = str(
        data.get("referred_by", "")
    ).strip().upper()

    if not referred_by:
        referred_by = session.get(
            "referral_code",
            ""
        ).strip().upper()

    # --------------------------------------------------------
    # VALIDATION
    # --------------------------------------------------------

    if not name:

        return jsonify({
            "success": False,
            "message": "Please enter your name."
        }), 400


    if len(name) > 80:

        return jsonify({
            "success": False,
            "message": "Name is too long."
        }), 400


    if not valid_email(email):

        return jsonify({
            "success": False,
            "message":
                "Please enter a valid email address."
        }), 400


    if len(username) > 30:

        return jsonify({
            "success": False,
            "message":
                "Username is too long."
        }), 400


    # --------------------------------------------------------
    # DATABASE
    # --------------------------------------------------------

    connection = get_db()


    # --------------------------------------------------------
    # DUPLICATE EMAIL
    # --------------------------------------------------------

    existing = connection.execute(
        """
        SELECT id
        FROM users
        WHERE email = ?
        """,
        (email,)
    ).fetchone()

    if existing:

        connection.close()

        return jsonify({
            "success": False,
            "message":
                "This email is already registered."
        }), 409


    # --------------------------------------------------------
    # REFERRER
    # --------------------------------------------------------

    valid_referrer = None

    if referred_by:

        referrer = connection.execute(
            """
            SELECT referral_code
            FROM users
            WHERE referral_code = ?
            AND is_verified = 1
            """,
            (referred_by,)
        ).fetchone()

        if referrer:

            valid_referrer = (
                referrer["referral_code"]
            )


    # --------------------------------------------------------
    # CREATE USER DATA
    # --------------------------------------------------------

    user_id = generate_user_id()

    referral_code = generate_code()

    verification_token = (
        secrets.token_urlsafe(32)
    )


    # --------------------------------------------------------
    # QUEUE POSITION
    # --------------------------------------------------------

    position_result = connection.execute(
        """
        SELECT COUNT(*)
        FROM users
        """
    ).fetchone()

    queue_position = (
        position_result[0] + 1
    )


    # --------------------------------------------------------
    # INSERT USER
    # --------------------------------------------------------

    try:

        connection.execute(
            """
            INSERT INTO users (
                user_id,
                name,
                email,
                username,
                referral_code,
                referred_by,
                queue_position,
                verification_token
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name,
                email,
                username
                if username
                else None,
                referral_code,
                valid_referrer,
                queue_position,
                verification_token
            )
        )

        connection.commit()

    except sqlite3.IntegrityError:

        connection.close()

        return jsonify({
            "success": False,
            "message":
                "Registration could not be completed."
        }), 409


    # --------------------------------------------------------
    # VERIFICATION URL
    # --------------------------------------------------------

    verification_url = url_for(
        "verify_email",
        token=verification_token,
        _external=True
    )


    # --------------------------------------------------------
    # CHECK RESEND
    # --------------------------------------------------------

    if not RESEND_API_KEY:

        connection.execute(
            """
            DELETE FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )

        connection.commit()
        connection.close()

        return jsonify({
            "success": False,
            "message":
                "Email service is not configured."
        }), 500


# ============================================================
# END OF PART 1
# ============================================================
# ============================================================
# SEND VERIFICATION EMAIL
# ============================================================

    try:

        email_response = resend.Emails.send({

            "from":
                RESEND_FROM_EMAIL,

            "to":
                [email],

            "subject":
                "Verify your ORQELETH AI registration",

            "html": f"""
                <div style="
                    font-family: Arial, sans-serif;
                    max-width: 600px;
                    margin: 40px auto;
                    padding: 40px;
                    background: #0b0b12;
                    color: #ffffff;
                    border-radius: 18px;
                ">

                    <h1 style="
                        color: #b875ff;
                        margin-bottom: 10px;
                    ">
                        ORQELETH AI
                    </h1>

                    <h2>
                        You're almost in.
                    </h2>

                    <p>
                        Hi {name},
                    </p>

                    <p>
                        Thanks for joining the
                        ORQELETH AI Founding 100 queue.
                    </p>

                    <p>
                        Your current queue position is:
                        <strong>#{queue_position}</strong>
                    </p>

                    <p>
                        Click the button below to
                        verify your email address.
                    </p>

                    <p style="
                        margin: 30px 0;
                    ">

                        <a
                            href="{verification_url}"
                            style="
                                display: inline-block;
                                padding: 15px 25px;
                                background: #8b4dff;
                                color: #ffffff;
                                text-decoration: none;
                                border-radius: 10px;
                                font-weight: bold;
                            "
                        >
                            VERIFY EMAIL →
                        </a>

                    </p>

                    <p style="
                        color: #999999;
                        font-size: 13px;
                    ">
                        If you did not register for
                        ORQELETH AI, you can safely
                        ignore this email.
                    </p>

                </div>
            """
        })

        print(
            "EMAIL SENT:",
            email_response
        )


    except Exception as error:

        print(
            "EMAIL ERROR:",
            repr(error)
        )

        # Remove failed registration.
        connection.execute(
            """
            DELETE FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )

        connection.commit()
        connection.close()

        return jsonify({
            "success": False,
            "message":
                "We could not send the verification email. "
                "Please try again."
        }), 500


    # ========================================================
    # SUCCESS
    # ========================================================

    connection.close()

    return jsonify({

        "success":
            True,

        "message":
            "Registration received. "
            "Check your email to verify.",

        "user_id":
            user_id,

        "queue_position":
            queue_position,

        "referral_code":
            referral_code,

        "verified":
            False,

        "verification_url":
            verification_url
    })


# ============================================================
# EMAIL VERIFICATION
# ============================================================

@app.route(
    "/verify/<token>"
)
def verify_email(token):

    connection = get_db()

    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE verification_token = ?
        """,
        (token,)
    ).fetchone()


    # --------------------------------------------------------
    # INVALID TOKEN
    # --------------------------------------------------------

    if not user:

        connection.close()

        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Invalid Verification</title>
        </head>

        <body style="
            background:#050509;
            color:white;
            font-family:Arial,sans-serif;
            text-align:center;
            padding:80px 20px;
        ">

            <h1>
                Invalid verification link
            </h1>

            <p>
                This verification link is invalid
                or has already been used.
            </p>

            <a
                href="/"
                style="color:#a875ff;"
            >
                Return to ORQELETH AI
            </a>

        </body>
        </html>
        """, 400


    # --------------------------------------------------------
    # ALREADY VERIFIED
    # --------------------------------------------------------

    if user["is_verified"] == 1:

        session["user_id"] = (
            user["user_id"]
        )

        connection.close()

        return redirect(
            "/dashboard"
        )


    # --------------------------------------------------------
    # VERIFY USER
    # --------------------------------------------------------

    connection.execute(
        """
        UPDATE users
        SET
            is_verified = 1,
            verification_token = NULL
        WHERE id = ?
        """,
        (user["id"],)
    )


    # --------------------------------------------------------
    # COUNT REFERRAL
    # --------------------------------------------------------

    if user["referred_by"]:

        referrer = connection.execute(
            """
            SELECT id
            FROM users
            WHERE referral_code = ?
            AND is_verified = 1
            AND id != ?
            """,
            (
                user["referred_by"],
                user["id"]
            )
        ).fetchone()

        if referrer:

            connection.execute(
                """
                UPDATE users
                SET verified_referrals =
                    verified_referrals + 1
                WHERE id = ?
                """,
                (referrer["id"],)
            )


    connection.commit()

    session["user_id"] = (
        user["user_id"]
    )

    connection.close()


    # --------------------------------------------------------
    # VERIFIED PAGE
    # --------------------------------------------------------

    return render_template(
        "verify.html"
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect("/")


    connection = get_db()

    user = connection.execute(
        """
        SELECT *
        FROM users
        WHERE user_id = ?
        AND is_verified = 1
        """,
        (session["user_id"],)
    ).fetchone()


    if not user:

        connection.close()

        session.clear()

        return redirect("/")


    # ========================================================
    # LEADERBOARD RANK
    # ========================================================

    rank_result = connection.execute(
        """
        SELECT COUNT(*) + 1
        FROM users AS other
        WHERE other.is_verified = 1
        AND (
            other.verified_referrals > ?
            OR (
                other.verified_referrals = ?
                AND other.created_at < ?
            )
        )
        """,
        (
            user["verified_referrals"],
            user["verified_referrals"],
            user["created_at"]
        )
    ).fetchone()


    rank = rank_result[0]


    # ========================================================
    # REFERRALS NEEDED
    # ========================================================

    referrals_needed = 0


    if rank > 100:

        top_100_user = connection.execute(
            """
            SELECT verified_referrals
            FROM users
            WHERE is_verified = 1
            ORDER BY
                verified_referrals DESC,
                created_at ASC
            LIMIT 1 OFFSET 99
            """
        ).fetchone()


        if top_100_user:

            referrals_needed = max(
                top_100_user["verified_referrals"]
                - user["verified_referrals"]
                + 1,
                0
            )

        else:

            referrals_needed = max(
                1 - user["verified_referrals"],
                0
            )


    # ========================================================
    # REFERRAL LINK
    # ========================================================

    referral_link = (
        url_for(
            "home",
            _external=True
        )
        + "?ref="
        + user["referral_code"]
    )


    connection.close()


    return render_template(
        "dashboard.html",

        name=user["name"],

        email=user["email"],

        rank=rank,

        queue_position=user["queue_position"],

        verified_referrals=user["verified_referrals"],

        referrals_needed=referrals_needed,

        referral_code=user["referral_code"],

        referral_link=referral_link
    )


# ============================================================
# STARTUP
# ============================================================

init_database()


# ============================================================
# LOCAL DEVELOPMENT
# ============================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.getenv(
                "PORT",
                "5000"
            )
        ),
        debug=True
    )