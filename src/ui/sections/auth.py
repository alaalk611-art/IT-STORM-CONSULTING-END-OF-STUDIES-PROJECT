# -*- coding: utf-8 -*-
# ============================================================
# Path: src/ui/sections/auth.py
# Role: Authentification "triple barrière" :
#   1) Login + mot de passe + captcha image (lettres)
#   2) Code Google Authenticator (TOTP + QR)
#   3) Code envoyé par email (6 chiffres, valide 5 minutes)
#
# Etat stocké dans st.session_state :
#   - "is_authenticated": bool
#   - "auth_step": 1, 2 ou 3
#   - "captcha_text": chaîne de lettres
#   - "email_otp": code email
#   - "email_otp_expires_at": timestamp
# ============================================================

from __future__ import annotations
import os
import time
import random
import string
import smtplib
from email.mime.text import MIMEText
from io import BytesIO

import streamlit as st

# =========================
# Imports TOTP / QR / CAPTCHA image
# =========================
try:
    import pyotp
except Exception:
    pyotp = None  # type: ignore

try:
    import qrcode
except Exception:
    qrcode = None  # type: ignore

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:
    Image = None  # type: ignore
    ImageDraw = None  # type: ignore
    ImageFont = None  # type: ignore

# =========================
# I18N local (FR / EN)
# =========================

_LANG_AUTH = {
    "en": {
        "auth_title": "Secure access",
        "auth_user": "Username",
        "auth_password": "Password",
        "auth_email_code": "Verification code received by email",
        "auth_submit_login": "Sign in",
        "auth_submit_totp": "Confirm Google Authenticator code",
        "auth_submit_code": "Confirm email code",
        "auth_resend_code": "Resend code",
        "auth_success": "Authentication successful. You now have access to the features.",
        "auth_error_login": "Invalid username or password.",
        "auth_error_code": "Invalid verification code.",
        "auth_error_code_expired": "The verification code has expired. Please request a new one.",
        "auth_error_totp": "Invalid Google Authenticator code.",
        "auth_required": "Please sign in with multi-factor authentication to access this tab.",
        "auth_logout": "Sign out",
        "auth_logged_in": "Connected",
        "auth_step1_title": "Step 1 · Login + captcha",
        "auth_step2_title": "Step 2 · Google Authenticator",
        "auth_step3_title": "Step 3 · Email verification",
        "auth_email_sent": "A verification code has been sent to your email address. It is valid for 5 minutes.",
        "auth_email_sent_to": "A verification code has been sent to:",
        "auth_email_error_send": "Error while sending the verification email. Please contact the administrator.",
        "auth_captcha_label": "Enter the letters shown in the image (uppercase or lowercase):",
        "auth_captcha_error": "Invalid captcha. Please try again.",
        "auth_totp_info": "Open Google Authenticator and enter the 6-digit code for this account.",
        "auth_totp_enabled": "Time-based authentication (Google Authenticator) is enabled for this account.",
        "auth_totp_scan": "Scan this QR code with Google Authenticator (or similar) if not already enrolled:",
        "auth_totp_uri": "Or add this key manually in your TOTP app:",
        "auth_qr_error_lib": "QR code generation is not available. Please install 'qrcode' and 'pillow' in the current virtualenv.",
        "auth_qr_error_generic": "QR rendering error:",
    },
    "fr": {
        "auth_title": "Accès sécurisé",
        "auth_user": "Identifiant",
        "auth_password": "Mot de passe",
        "auth_email_code": "Code de vérification reçu par email",
        "auth_submit_login": "Se connecter",
        "auth_submit_totp": "Valider le code Google Authenticator",
        "auth_submit_code": "Valider le code email",
        "auth_resend_code": "Renvoyer un code",
        "auth_success": "Authentification réussie. Vous avez maintenant accès aux fonctionnalités.",
        "auth_error_login": "Identifiant ou mot de passe incorrect.",
        "auth_error_code": "Code de vérification invalide.",
        "auth_error_code_expired": "Le code de vérification a expiré. Merci d'en demander un nouveau.",
        "auth_error_totp": "Code Google Authenticator invalide.",
        "auth_required": "Veuillez vous connecter avec l'authentification multi-facteurs pour accéder à cet onglet.",
        "auth_logout": "Se déconnecter",
        "auth_logged_in": "Connecté",
        "auth_step1_title": "Étape 1 · Connexion + captcha",
        "auth_step2_title": "Étape 2 · Google Authenticator",
        "auth_step3_title": "Étape 3 · Vérification par email",
        "auth_email_sent": "Un code de vérification vient d'être envoyé à votre adresse email. Il est valable 5 minutes.",
        "auth_email_sent_to": "Un code de vérification a été envoyé à :",
        "auth_email_error_send": "Erreur lors de l'envoi de l'email de vérification. Merci de contacter l'administrateur.",
        "auth_captcha_label": "Recopiez les lettres affichées dans l'image (majuscule ou minuscule) :",
        "auth_captcha_error": "Captcha incorrect. Merci de réessayer.",
        "auth_totp_info": "Ouvrez Google Authenticator et saisissez le code à 6 chiffres pour ce compte.",
        "auth_totp_enabled": "L’authentification par code temporel (Google Authenticator) est activée pour ce compte.",
        "auth_totp_scan": "Scannez ce QR code avec Google Authenticator (ou équivalent) si vous n’êtes pas encore inscrit :",
        "auth_totp_uri": "Ou ajoutez cette clé manuellement dans votre application TOTP :",
        "auth_qr_error_lib": "La génération de QR Code n’est pas disponible. Installez 'qrcode' et 'pillow' dans le virtualenv courant.",
        "auth_qr_error_generic": "Erreur lors de l’affichage du QR Code :",
    },
}


def _t_auth(key: str) -> str:
    """Mini i18n locale: se base sur st.session_state['lang'] si présent."""
    lang = st.session_state.get("lang", "fr")
    return _LANG_AUTH.get(lang, _LANG_AUTH["fr"]).get(key, key)


# =========================
# Helpers d'état
# =========================

def init_auth_state() -> None:
    """Initialise les clés d'authentification dans la session."""
    st.session_state.setdefault("is_authenticated", False)
    st.session_state.setdefault("auth_step", 1)


def _check_login_credentials(username: str, password: str) -> bool:
    """
    Vérifie identifiant + mot de passe (1er facteur).
    Utilise les variables d'environnement :
      - SC_LOGIN_USER
      - SC_LOGIN_PASSWORD
    """
    expected_user = os.getenv("SC_LOGIN_USER", "admin")
    expected_pwd = os.getenv("SC_LOGIN_PASSWORD", "changeme")
    return username == expected_user and password == expected_pwd


# =========================
# CAPTCHA image (lettres)
# =========================

_CAPTCHA_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"


def _reset_captcha() -> None:
    """Génère un nouveau texte de captcha."""
    text = "".join(random.choice(_CAPTCHA_CHARS) for _ in range(5))
    st.session_state["captcha_text"] = text


def _ensure_captcha() -> None:
    """S'assure qu'un captcha existe dans la session."""
    if "captcha_text" not in st.session_state:
        _reset_captcha()


def _generate_captcha_image(text: str) -> bytes | None:
    """
    Génère une image simple avec le texte du captcha.
    Retourne des bytes PNG, ou None si PIL n'est pas dispo.
    """
    if Image is None or ImageDraw is None or ImageFont is None:
        return None

    width, height = 200, 60
    img = Image.new("RGB", (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)

    # Bruit léger (lignes)
    for _ in range(5):
        x1 = random.randint(0, width)
        y1 = random.randint(0, height)
        x2 = random.randint(0, width)
        y2 = random.randint(0, height)
        draw.line((x1, y1, x2, y2), fill=(200, 200, 200), width=1)

    # Texte centré approximativement
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    text = text.upper()

    # Pillow >= 10 : textsize supprimé → on utilise textbbox
    try:
        if hasattr(draw, "textbbox"):
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        else:
            # Compatibilité anciennes versions
            text_w, text_h = draw.textsize(text, font=font)  # type: ignore[attr-defined]
    except Exception:
        # Fallback simple si ça plante
        text_w = len(text) * 12
        text_h = 20

    x = (width - text_w) / 2
    y = (height - text_h) / 2
    draw.text((x, y), text, fill=(0, 0, 0), font=font)

    # Export PNG en mémoire
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()

def _check_captcha(user_input: str) -> bool:
    """Vérifie que la réponse utilisateur correspond au texte du captcha."""
    text = st.session_state.get("captcha_text")
    if not text:
        return False
    return user_input.strip().upper() == text.upper()


# =========================
# TOTP (Google Authenticator)
# =========================

def _is_totp_enabled() -> bool:
    """Retourne True si on a un secret TOTP et pyotp installé."""
    secret = os.getenv("SC_TOTP_SECRET")
    return bool(secret and pyotp is not None)


def _render_totp_qr_forced() -> None:
    """
    Affiche un QR Code TOTP si possible + la clé secrète.
    QR forcé (pas de SC_TOTP_SHOW_QR).
    """
    if not _is_totp_enabled():
        return

    secret = os.getenv("SC_TOTP_SECRET", "")
    if not secret:
        return

    issuer = os.getenv("SC_TOTP_ISSUER", "StormCopilot")
    account = os.getenv("SC_TOTP_ACCOUNT", "user@it-storm")

    st.info(_t_auth("auth_totp_enabled"))

    if pyotp is None or qrcode is None:
        st.error(_t_auth("auth_qr_error_lib"))
        st.markdown(_t_auth("auth_totp_uri"))
        st.code(secret, language="text")
        return

    # URI TOTP
    try:
        totp = pyotp.TOTP(secret)  # type: ignore
        uri = totp.provisioning_uri(name=account, issuer_name=issuer)
    except Exception as e:
        st.warning(f"{_t_auth('auth_qr_error_generic')} {e}")
        st.markdown(_t_auth("auth_totp_uri"))
        st.code(secret, language="text")
        return

    # Génération du QR + affichage
    try:
        st.markdown(_t_auth("auth_totp_scan"))
        qr_img = qrcode.make(uri)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        img_bytes = buf.getvalue()
        st.image(img_bytes, caption=f"{issuer} · {account}", width=250)
    except Exception as e:
        st.warning(f"{_t_auth('auth_qr_error_generic')} {e}")

    st.markdown(_t_auth("auth_totp_uri"))
    st.code(secret, language="text")


def _check_totp_code(otp: str) -> bool:
    """Vérifie le code TOTP (Google Authenticator)."""
    if not _is_totp_enabled():
        return False
    secret = os.getenv("SC_TOTP_SECRET", "")
    if not secret:
        return False
    try:
        totp = pyotp.TOTP(secret)  # type: ignore
        # fenêtre de tolérance d'un pas (30s)
        return bool(totp.verify(otp.strip(), valid_window=1))
    except Exception:
        return False


# =========================
# Email OTP (3e facteur)
# =========================

def _generate_email_code(length: int = 6) -> str:
    """Génère un code numérique aléatoire (par défaut 6 chiffres)."""
    return "".join(random.choice(string.digits) for _ in range(length))


def _send_email_code(code: str) -> bool:
    """
    Envoie le code par email en utilisant les variables d'environnement :

      SC_EMAIL_SMTP_HOST
      SC_EMAIL_SMTP_PORT
      SC_EMAIL_SMTP_USER
      SC_EMAIL_SMTP_PASSWORD
      SC_EMAIL_FROM
      SC_EMAIL_TO
      SC_EMAIL_SUBJECT
    """
    smtp_host = os.getenv("SC_EMAIL_SMTP_HOST", "")
    smtp_port = int(os.getenv("SC_EMAIL_SMTP_PORT", "587"))
    smtp_user = os.getenv("SC_EMAIL_SMTP_USER", "")
    smtp_pwd = os.getenv("SC_EMAIL_SMTP_PASSWORD", "")
    mail_from = os.getenv("SC_EMAIL_FROM", smtp_user)
    mail_to = os.getenv("SC_EMAIL_TO", "")

    if not smtp_host or not smtp_user or not smtp_pwd or not mail_to:
        return False

    subject = os.getenv("SC_EMAIL_SUBJECT", "Votre code de vérification")

    body = (
        f"Bonjour,\n\n"
        f"Voici votre code de connexion à StormCopilot : {code}\n\n"
        f"Ce code est valable 5 minutes.\n\n"
        f"Cordialement,\n"
        f"L'assistant StormCopilot"
    )

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pwd)
            server.send_message(msg)
        return True
    except Exception as e:
        st.error(f"Email error: {e}")
        return False


def _start_email_otp_flow() -> None:
    """Génère un code email, l'envoie et passe à l'étape 3."""
    code = _generate_email_code()
    st.session_state["email_otp"] = code
    st.session_state["email_otp_expires_at"] = time.time() + 300  # 5 minutes

    ok = _send_email_code(code)
    if not ok:
        st.error(_t_auth("auth_email_error_send"))
    else:
        st.info(_t_auth("auth_email_sent"))

    st.session_state["auth_step"] = 3


def _check_email_code(user_input: str) -> str:
    """
    Vérifie le code saisi par l'utilisateur.
    Retourne:
      - "ok" si le code est valide
      - "expired" si le code a expiré
      - "invalid" sinon
    """
    code = st.session_state.get("email_otp")
    expires_at = st.session_state.get("email_otp_expires_at", 0)

    if not code or not expires_at:
        return "invalid"

    now = time.time()
    if now > expires_at:
        return "expired"

    if user_input.strip() == code:
        return "ok"
    return "invalid"


# =========================
# UI Sidebar & Gate
# =========================

def render_auth_sidebar() -> None:
    """
    Petit bloc d'état dans la sidebar : connecté / pas connecté + bouton logout.
    À appeler depuis app.py dans la sidebar.
    """
    init_auth_state()

    st.sidebar.markdown("---")
    if st.session_state.get("is_authenticated"):
        st.sidebar.success(_t_auth("auth_logged_in"))
        if st.sidebar.button(_t_auth("auth_logout"), key="btn_logout"):
            st.session_state["is_authenticated"] = False
            st.session_state["auth_step"] = 1
            st.session_state.pop("email_otp", None)
            st.session_state.pop("email_otp_expires_at", None)
            st.session_state.pop("captcha_text", None)
            st.rerun()
    else:
        st.sidebar.info(_t_auth("auth_required"))


def render_auth_gate() -> bool:
    """
    Gate principal pour un onglet protégé.
    - Si l'utilisateur est déjà authentifié -> True
    - Sinon :
        Étape 1 : login + mot de passe + captcha image
        Étape 2 : code Google Authenticator
        Étape 3 : code email
    """
    init_auth_state()

    if st.session_state.get("is_authenticated"):
        return True

    st.markdown(f"#### 🔐 {_t_auth('auth_title')}")

    step = st.session_state.get("auth_step", 1)

    # =========================
    # Étape 1 : login / mot de passe + captcha image
    # =========================
    if step == 1:
        st.markdown(f"**{_t_auth('auth_step1_title')}**")

        # Génère / charge captcha
        _ensure_captcha()
        captcha_text = st.session_state.get("captcha_text", "ERROR")
        img_bytes = _generate_captcha_image(captcha_text)

        # ============================
        #  FORMULAIRE LOGIN + CAPTCHA
        # ============================
        with st.form("login_form_step1"):
            # Username / Password
            user = st.text_input(_t_auth("auth_user"), key="auth_user")
            pwd = st.text_input(_t_auth("auth_password"), type="password", key="auth_pwd")

            # Image captcha JUSTE AVANT le champ input
            if img_bytes is not None:
                st.image(img_bytes, caption="CAPTCHA", width=260)

            # Champ texte du captcha
            captcha_label = _t_auth("auth_captcha_label")
            captcha_input = st.text_input(captcha_label, key="auth_captcha")

            submitted = st.form_submit_button(_t_auth("auth_submit_login"))

        # ====================================
        #  VALIDATION DU CAPTCHA + CREDENTIALS
        # ====================================
        if submitted:
            # Vérifier captcha en premier
            if not _check_captcha(captcha_input):
                st.error(_t_auth("auth_captcha_error"))
                _reset_captcha()
            else:
                # Vérifier login/password
                if _check_login_credentials(user, pwd):
                    st.session_state["auth_step"] = 2  # Passage TOTP
                    st.rerun()
                else:
                    st.error(_t_auth("auth_error_login"))
                    _reset_captcha()

        return False

    # =========================
    # Étape 2 : TOTP (Google Authenticator)
    # =========================
    if step == 2:
        st.markdown(f"**{_t_auth('auth_step2_title')}**")

        if not _is_totp_enabled():
            st.warning("TOTP non configuré (SC_TOTP_SECRET manquant ou pyotp absent). Passage direct à l'étape email.")
            _start_email_otp_flow()
            st.rerun()
            return False

        _render_totp_qr_forced()
        st.caption(_t_auth("auth_totp_info"))

        with st.form("login_form_step2_totp"):
            totp_input = st.text_input("Code Google Authenticator", key="auth_totp")
            submitted_totp = st.form_submit_button(_t_auth("auth_submit_totp"))

        if submitted_totp:
            if _check_totp_code(totp_input):
                # Code TOTP OK → lancer le flux email (étape 3)
                _start_email_otp_flow()
                st.rerun()
            else:
                st.error(_t_auth("auth_error_totp"))

        return False

    # =========================
    # Étape 3 : code email
    # =========================
    if step == 3:
        st.markdown(f"**{_t_auth('auth_step3_title')}**")

        mail_to = os.getenv("SC_EMAIL_TO", "")
        if mail_to:
            st.caption(f"{_t_auth('auth_email_sent_to')} `{mail_to}`")
        else:
            st.caption(_t_auth("auth_email_sent"))

        col1, col2 = st.columns([2, 1])

        with col1:
            with st.form("login_form_step3_email"):
                code_input = st.text_input(_t_auth("auth_email_code"), key="auth_email_code")
                submitted_code = st.form_submit_button(_t_auth("auth_submit_code"))

        with col2:
            if st.button(_t_auth("auth_resend_code"), key="btn_resend_code"):
                _start_email_otp_flow()
                st.rerun()

        if submitted_code:
            status = _check_email_code(code_input)

            if status == "ok":
                st.session_state["is_authenticated"] = True
                st.session_state.pop("email_otp", None)
                st.session_state.pop("email_otp_expires_at", None)
                st.success(_t_auth("auth_success"))
                st.rerun()
            elif status == "expired":
                st.error(_t_auth("auth_error_code_expired"))
            else:
                st.error(_t_auth("auth_error_code"))

        return False

    # Fallback : step incohérent → reset
    st.session_state["auth_step"] = 1
    return False
# End of src/ui/sections/auth.py