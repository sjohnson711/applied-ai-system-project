import hashlib
import streamlit as st
from pawpal.services.database import create_user, get_user


def _hash(password: str) -> str:
    salt = b"pawpalplus_2026"
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000).hex()


def is_logged_in() -> bool:
    return bool(st.session_state.get("user_email"))


def logout() -> None:
    st.session_state.clear()
    st.rerun()


@st.dialog("🐾 Welcome to PawPal+")
def show_login_modal() -> None:
    tab1, tab2 = st.tabs(["Sign In", "Create Account"])

    with tab1:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Sign In", key="login_btn", use_container_width=True):
            if not email or not password:
                st.warning("Please enter your email and password.")
                return
            user = get_user(email.strip().lower())
            if user and user["password_hash"] == _hash(password):
                st.session_state.user_email = user["email"]
                st.session_state.user_name = user["name"]
                st.rerun()
            else:
                st.error("Invalid email or password.")

    with tab2:
        name = st.text_input("Your name", key="reg_name")
        email = st.text_input("Email", key="reg_email")
        password = st.text_input("Password", type="password", key="reg_password")
        confirm = st.text_input("Confirm password", type="password", key="reg_confirm")
        if st.button("Create Account", key="reg_btn", use_container_width=True):
            if not name or not email or not password:
                st.warning("All fields are required.")
                return
            if password != confirm:
                st.error("Passwords do not match.")
                return
            if len(password) < 6:
                st.error("Password must be at least 6 characters.")
                return
            ok = create_user(email.strip().lower(), name.strip(), _hash(password))
            if ok:
                st.session_state.user_email = email.strip().lower()
                st.session_state.user_name = name.strip()
                st.rerun()
            else:
                st.error("An account with that email already exists.")
