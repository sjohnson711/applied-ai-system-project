import re
import secrets
import hashlib
import streamlit as st
from pawpal.services.database import (
    create_user,
    get_user_by_username,
    get_user_by_email,
    update_password,
)
from pawpal.services.email_service import send_recovery_email

# ─── Validation helpers ───────────────────────────────────────────────────────

# Username: 3–20 chars, must start with a letter, letters/digits/underscores only
_USERNAME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]{2,19}$')

# At least one symbol from a broad set
_SYMBOL_RE = re.compile(r'[!@#$%^&*()\-_=+\[\]{}|;\':",.<>?/\\`~]')


def _validate_username(username: str) -> list[str]:
    """Return a list of rule-violation messages; empty list means valid."""
    if not _USERNAME_RE.match(username):
        return [
            "Username must be 3–20 characters, start with a letter, "
            "and contain only letters, numbers, and underscores."
        ]
    return []


def _validate_password(password: str) -> list[str]:
    """Return a list of rule-violation messages; empty list means valid."""
    errors = []
    if len(password) < 8 or len(password) > 12:
        errors.append("Password must be 8–12 characters long.")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number.")
    if not _SYMBOL_RE.search(password):
        errors.append("Password must contain at least one symbol (e.g. !@#$%).")
    return errors


# ─── Password hashing ─────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    salt = b"pawpalplus_2026"
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()


# ─── Session helpers ──────────────────────────────────────────────────────────

def is_logged_in() -> bool:
    return bool(st.session_state.get("user_email"))


def logout() -> None:
    st.session_state.clear()
    st.rerun()


# ─── Login modal (3 views) ────────────────────────────────────────────────────

@st.dialog("🐾 Welcome to PawPal+")
def show_login_modal() -> None:
    """3-view dialog: sign in / create account / account recovery.

    The active view is controlled by st.session_state.modal_view.
    """
    view = st.session_state.get("modal_view", "signin")

    # ── View: Sign In ─────────────────────────────────────────────────────────
    if view == "signin":
        st.subheader("Sign In")
        username = st.text_input("Username", key="signin_username")
        password = st.text_input("Password", type="password", key="signin_password")

        if st.button("Sign In", key="signin_btn", use_container_width=True, type="primary"):
            if not username or not password:
                st.warning("Please enter your username and password.")
                return
            user = get_user_by_username(username)
            if user and user["password_hash"] == _hash(password):
                st.session_state.user_email    = user["email"]
                st.session_state.user_name     = user["name"]
                st.session_state.user_username = user["username"]
                st.session_state.modal_view    = "welcome"
                st.rerun()
            else:
                st.error("Incorrect username or password.")

        st.markdown("---")
        col_forgot, col_create = st.columns(2)
        with col_forgot:
            if st.button("Forgot password?", key="goto_recover_btn", use_container_width=True):
                st.session_state.modal_view = "recover"
                st.rerun()
        with col_create:
            if st.button("Create account", key="goto_create_btn", use_container_width=True):
                st.session_state.modal_view = "create"
                st.rerun()

    # ── View: Create Account ──────────────────────────────────────────────────
    elif view == "create":
        st.subheader("Create Account")
        name     = st.text_input("Your name",       key="reg_name")
        username = st.text_input("Username",         key="reg_username",
                                 help="3–20 chars · letters, numbers, underscores · must start with a letter")
        email    = st.text_input("Email",            key="reg_email")
        password = st.text_input("Password",         type="password", key="reg_password",
                                 help="8–12 chars · 1 uppercase · 1 lowercase · 1 number · 1 symbol")
        confirm  = st.text_input("Confirm password", type="password", key="reg_confirm")

        if st.button("Create Account", key="reg_btn", use_container_width=True, type="primary"):
            errors = []
            if not name or not username or not email or not password:
                errors.append("All fields are required.")
            else:
                errors += _validate_username(username)
                errors += _validate_password(password)
                if password != confirm:
                    errors.append("Passwords do not match.")

            if errors:
                for err in errors:
                    st.error(err)
                return

            ok = create_user(
                email.strip().lower(),
                username.strip().lower(),
                name.strip(),
                _hash(password),
            )
            if ok:
                st.session_state.user_email    = email.strip().lower()
                st.session_state.user_name     = name.strip()
                st.session_state.user_username = username.strip().lower()
                st.session_state.modal_view    = "welcome"
                st.rerun()
            else:
                st.error("That email or username is already taken. Please choose another.")

        st.markdown("---")
        if st.button("← Back to Sign In", key="back_to_signin_btn", use_container_width=True):
            st.session_state.modal_view = "signin"
            st.rerun()

    # ── View: Account Recovery ────────────────────────────────────────────────
    elif view == "recover":
        st.subheader("Account Recovery")
        st.caption(
            "Enter your email address. We'll send you your username and a temporary password."
        )
        email = st.text_input("Email", key="recover_email")

        if st.button("Send Recovery Email", key="recover_btn", use_container_width=True, type="primary"):
            if not email:
                st.warning("Please enter your email address.")
                return
            user = get_user_by_email(email.strip().lower())
            if not user:
                st.error("No account found with that email address.")
                return

            # Generate a temporary password guaranteed to meet all rules:
            # "!" prefix (symbol) + 7 urlsafe chars (mixed case + digits from base64)
            # We append a digit to be safe since urlsafe_b64 may not include one.
            raw = secrets.token_urlsafe(8)[:7]
            temp_pw = "!" + raw + "1A"  # guarantees symbol, digit, uppercase
            temp_pw = temp_pw[:12]       # cap at 12

            update_password(user["email"], _hash(temp_pw))
            ok, _ = send_recovery_email(user["email"], user["username"], temp_pw)

            if ok:
                st.success(
                    "Recovery email sent — check your inbox. "
                    "Sign in with your username and the temporary password."
                )
            else:
                # Fallback: show username directly when Resend is not configured
                st.warning(
                    f"Email delivery unavailable. Your username is: **{user['username']}**  \n"
                    f"A temporary password has been set — please contact support to retrieve it."
                )

        st.markdown("---")
        if st.button("← Back to Sign In", key="back_from_recover_btn", use_container_width=True):
            st.session_state.modal_view = "signin"
            st.rerun()

    # ── View: Welcome ─────────────────────────────────────────────────────────
    elif view == "welcome":
        owner_name = st.session_state.get("user_name") or st.session_state.get("user_username", "")
        st.markdown(
            f"<h3 style='margin:0 0 0.25rem 0;'>Welcome back, {owner_name}! 🐾</h3>"
            "<p style='color:#64748b;margin:0;'>Your pets are counting on you — let's see what's ahead.</p>",
            unsafe_allow_html=True,
        )
        st.write("")
        if st.button("Let's go! 🐾", use_container_width=True, type="primary"):
            st.session_state.modal_open  = False
            st.session_state.modal_view  = "signin"
            st.session_state.show_briefing = True
            st.rerun()
