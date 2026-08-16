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

ROOT_ENV = BASE_DIR / ".env"
DATABASE_ENV = BASE_DIR / "database" / ".env"

if ROOT_ENV.exists():
    load_dotenv(ROOT_ENV)
elif DATABASE_ENV.exists():
    load_dotenv(DATABASE_ENV)
else:
    load_dotenv()


RESEND_API_KEY = os.getenv("RESEND_API_KEY")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
else:
    print("WARNING: RESEND_API_KEY was not found.")


# ============================================================
# FLASK
# ============================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    secrets.token_hex(32)
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_email
        ON users(email)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_referral_code
        ON users(referral_code)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_verified
        ON users(is_verified)
    """)

    connection.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_referrer
        ON users(referred_by)
    """)

    # --------------------------------------------------------
    # Older database compatibility
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

def generate_code(length=8):

    characters = (
        string.ascii_uppercase +
        string.digits
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


def generate_user_id():

    return "ORQ-" + secrets.token_hex(6).upper()


def valid_email(email):

    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

    return re.match(
        pattern,
        email
    ) is not None


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    # Support referral links such as:
    # http://127.0.0.1:5000/?ref=ABC12345

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
# REFERRAL LANDING
# ============================================================

@app.route("/queue/<referral_code>")
def referral_landing(referral_code):

    referral_code = (
        referral_code
        .strip()
        .upper()
    )

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

    return redirect("/")


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

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({

            "success": False,

            "message":
                "Invalid request."

        }), 400


    # --------------------------------------------------------
    # INPUT
    # --------------------------------------------------------

    name = str(
        data.get(
            "name",
            ""
        )
    ).strip()

    email = str(
        data.get(
            "email",
            ""
        )
    ).strip().lower()

    username = str(
        data.get(
            "username",
            ""
        )
    ).strip()

    referred_by = str(
        data.get(
            "referred_by",
            ""
        )
    ).strip().upper()


    # If frontend didn't send referral code,
    # use the referral stored in the session.

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

            "message":
                "Please enter your name."

        }), 400


    if len(name) > 80:

        return jsonify({

            "success": False,

            "message":
                "Name is too long."

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
            SELECT
                id,
                referral_code
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
    # USER CREATION
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
                username if username else None,
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
    # EMAIL CONFIGURATION
    # --------------------------------------------------------

    if not RESEND_API_KEY:

        print(
            "EMAIL ERROR: "
            "RESEND_API_KEY is missing."
        )

        connection.close()

        return jsonify({

            "success": False,

            "message":
                "Email service is not configured."

        }), 500


    # ========================================================
    # SEND EMAIL — ONLY ONCE
    # ========================================================
try:

    email_response = resend.Emails.send({
        "from": "ORQELETH AI <noreply@joinorqeleth.com>",
        "to": [email],
        "subject": "Verify your ORQELETH AI registration",
        "html": f"""
            <div style="
                font-family: Arial, sans-serif;
                max-width: 600px;
                margin: auto;
                    padding: 30px;
                    background: #0b0b12;
                    color: #ffffff;
                    border-radius: 16px;
                ">

                    <h1>
                        ORQELETH AI
                    </h1>

                    <h2>
                        Welcome, {name}.
                    </h2>

                    <p>
                        Your ORQELETH AI early-access
                        registration has been received.
                    </p>

                    <p>
                        Your current queue position:
                        <strong>
                            #{queue_position}
                        </strong>
                    </p>

                    <p>
                        Verify your email address
                        to confirm your registration.
                    </p>

                    <p style="margin: 30px 0;">

                        <a
                            href="{verification_url}"
                            style="
                                display: inline-block;
                                padding: 14px 24px;
                                background: #9b5cff;
                                color: #ffffff;
                                text-decoration: none;
                                border-radius: 10px;
                                font-weight: bold;
                            "
                        >
                            VERIFY EMAIL
                        </a>

                    </p>

                    <p style="
                        font-size: 13px;
                        color: #aaaaaa;
                    ">
                        If you did not register
                        for ORQELETH AI,
                        you can ignore this email.
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

        # Remove failed registration so the user
        # can try the same email again.

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


    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    connection.close()

    return jsonify({

        "success": True,

        "message":
            "Verification email sent.",

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
# END OF PART 1
# ============================================================
# ============================================================
# EMAIL VERIFICATION
# ============================================================

@app.route("/verify/<token>")
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

        <body>
            <h1>Invalid verification link</h1>

            <p>
                This verification link is invalid
                or has already been used.
            </p>

            <a href="/">
                Return to ORQELETH AI
            </a>
        </body>
        </html>
        """, 400


    # --------------------------------------------------------
    # ALREADY VERIFIED
    # --------------------------------------------------------

    if user["is_verified"] == 1:

        connection.close()

        session["user_id"] = user["user_id"]

        return redirect("/dashboard")


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


    # --------------------------------------------------------
    # CREATE LOGIN SESSION
    # --------------------------------------------------------

    session["user_id"] = user["user_id"]


    # Referral session is no longer needed
    session.pop(
        "referral_code",
        None
    )


    connection.close()


    # --------------------------------------------------------
    # SEND TO DASHBOARD
    # --------------------------------------------------------

    return redirect("/dashboard")


# ============================================================
# CURRENT USER / DASHBOARD DATA
# ============================================================

@app.route("/api/me")
def current_user():

    if "user_id" not in session:

        return jsonify({
            "success": False,
            "message": "Not authenticated."
        }), 401


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

        return jsonify({
            "success": False,
            "message": "Verified user not found."
        }), 401


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
    # REFERRALS NEEDED FOR TOP 100
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
                (
                    top_100_user["verified_referrals"]
                    -
                    user["verified_referrals"]
                    +
                    1
                ),
                0
            )

    else:

        referrals_needed = max(
            1 - user["verified_referrals"],
            0
        )


    # ========================================================
    # REWARD TIER
    # ========================================================

    if rank <= 25:

        reward_title = "1 Year Enterprise"

        reward_description = (
            "Rank #1–25: eligible for "
            "1 year of ORQELETH Enterprise "
            "plus the Founding 100 badge."
        )


    elif rank <= 50:

        reward_title = "6 Months Enterprise"

        reward_description = (
            "Rank #26–50: eligible for "
            "6 months of ORQELETH Enterprise "
            "plus the Founding 100 badge."
        )


    elif rank <= 75:

        reward_title = "3 Months Enterprise"

        reward_description = (
            "Rank #51–75: eligible for "
            "3 months of ORQELETH Enterprise "
            "plus the Founding 100 badge."
        )


    elif rank <= 100:

        reward_title = "1 Month Enterprise"

        reward_description = (
            "Rank #76–100: eligible for "
            "1 month of ORQELETH Enterprise "
            "plus the Founding 100 badge."
        )


    else:

        reward_title = "Keep Climbing"

        reward_description = (
            "Reach the Top 100 to become "
            "eligible for the Founding 100 "
            "rewards and badge."
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


    # ========================================================
    # DASHBOARD RESPONSE
    # ========================================================

    return jsonify({

        "success": True,

        "name":
            user["name"],

        "queue_position":
            user["queue_position"],

        "verified_referrals":
            user["verified_referrals"],

        "rank":
            rank,

        "referrals_needed":
            referrals_needed,

        "referral_code":
            user["referral_code"],

        "referral_link":
            referral_link,

        "reward_title":
            reward_title,

        "reward_description":
            reward_description
    })


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


    connection.close()


    if not user:

        session.clear()

        return redirect("/")


    return render_template(
        "dashboard.html",
        user=user
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")


# ============================================================
# REFERRAL INFORMATION
# ============================================================

@app.route("/api/referral")
def referral_info():

    if "user_id" not in session:

        return jsonify({
            "success": False,
            "message": "You are not logged in."
        }), 401


    connection = get_db()


    user = connection.execute(
        """
        SELECT
            referral_code,
            verified_referrals,
            queue_position
        FROM users
        WHERE user_id = ?
        AND is_verified = 1
        """,
        (session["user_id"],)
    ).fetchone()


    connection.close()


    if not user:

        return jsonify({
            "success": False,
            "message": "User not found."
        }), 404


    referral_link = (
        url_for(
            "home",
            _external=True
        )
        + "?ref="
        + user["referral_code"]
    )


    return jsonify({

        "success": True,

        "referral_code":
            user["referral_code"],

        "verified_referrals":
            user["verified_referrals"],

        "queue_position":
            user["queue_position"],

        "referral_link":
            referral_link
    })


# ============================================================
# START
# ============================================================

init_database()


if __name__ == "__main__":

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )