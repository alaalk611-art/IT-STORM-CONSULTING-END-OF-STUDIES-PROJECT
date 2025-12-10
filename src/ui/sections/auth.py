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
#   - "auth_just_logged_in": bool (bannière succès temporaire)
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


from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage


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
        "auth_totp_scan": "Scan this QR code with Google Authenticator to verify your identity:",
        "auth_qr_error_lib": "QR code generation is not available. Please install 'qrcode' and 'pillow'.",
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
        "auth_totp_scan": "Scannez ce QR code avec Google Authenticator pour vérifier votre identité :",
        "auth_qr_error_lib": "La génération de QR Code n’est pas disponible. Installez 'qrcode' et 'pillow'.",
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
    st.session_state.setdefault("auth_just_logged_in", False)


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
        return

    # URI TOTP
    try:
        totp = pyotp.TOTP(secret)  # type: ignore
        uri = totp.provisioning_uri(name=account, issuer_name=issuer)
    except Exception as e:
        st.warning(f"{_t_auth('auth_qr_error_generic')} {e}")
        return

    # Génération du QR + affichage
    try:
        st.markdown(_t_auth("auth_totp_scan"))
        qr_img = qrcode.make(uri)
        buf = BytesIO()
        qr_img.save(buf, format="PNG")
        buf.seek(0)
        img_bytes = buf.getvalue()
        col_left, col_center, col_right = st.columns([1, 2, 1])
        with col_center:
            st.markdown("<div class='qr-box'>", unsafe_allow_html=True)
            st.image(img_bytes, caption=f"{issuer} · {account}", width=250)
            st.markdown("</div>", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"{_t_auth('auth_qr_error_generic')} {e}")


def _check_totp_code(otp: str) -> bool:
    """Vérifie le code TOTP (Google Authenticator)."""
    if not _is_totp_enabled():
        return False
    secret = os.getenv("SC_TOTP_SECRET", "")
    if not secret:
        return False
    try:
        totp = pyotp.TOTP(secret)  # type: ignore
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
    Envoie le code par email avec un template HTML + logo IT STORM.

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

    subject = os.getenv("SC_EMAIL_SUBJECT", "Code de vérification StormCopilot")

    # ---------- corps texte (fallback) ----------
    text_body = (
        "Bonjour,\n\n"
        f"Voici votre code de connexion à StormCopilot : {code}\n\n"
        "Ce code est valable 5 minutes.\n\n"
        "Cordialement,\n"
        "L'assistant StormCopilot"
    )

    # ---------- chemin du logo ----------
    # Tu peux garder ton chemin absolu si tu préfères, mais voici une version relative :
    base_dir = os.path.dirname(__file__)
    logo_path = r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\src\ui\assets\itstorm_logo.png"
    logo_exists = os.path.exists(logo_path)


    # ---------- corps HTML ----------
    html_body = f"""
    <html>
      <body style="font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background-color:#f4f5f7; padding:24px;">
        <div style="max-width:520px;margin:0 auto;background-color:#ffffff;border-radius:12px;padding:24px 28px;box-shadow:0 8px 24px rgba(15,23,42,0.12);">
          
          <div style="text-align:center;margin-bottom:18px;">
            {"<img src='cid:itstorm_logo' alt='IT-STORM' style='height:52px;margin-bottom:10px;border-radius:12px;' />" if logo_exists else ""}
            <div style="font-size:22px;font-weight:700;color:#111827;margin-bottom:4px;">
              StormCopilot · Code de vérification
            </div>
            <div style="font-size:13px;color:#6b7280;">
              Vérification de votre identité pour l’accès sécurisé à StormCopilot.
            </div>
          </div>

          <div style="margin:20px 0;padding:18px;border-radius:10px;background:linear-gradient(135deg,#1d4ed8,#3b82f6);color:#ffffff;text-align:center;">
            <div style="font-size:13px;opacity:0.9;margin-bottom:6px;">Votre code de connexion</div>
            <div style="font-size:26px;font-weight:700;letter-spacing:0.28em;">
              {code}
            </div>
          </div>

          <p style="font-size:13px;color:#374151;line-height:1.5;margin:0 0 10px 0;">
            Ce code est valable <strong>5 minutes</strong>. Pour votre sécurité, ne le partagez avec personne.
          </p>
          <p style="font-size:13px;color:#6b7280;line-height:1.5;margin:0 0 18px 0;">
            Si vous n’êtes pas à l’origine de cette demande, vous pouvez ignorer cet email.
          </p>

          <hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0;" />

          <p style="font-size:11px;color:#9ca3af;line-height:1.5;margin:0;text-align:center;">
            StormCopilot · IT-STORM Consulting<br/>
            Email généré automatiquement, merci de ne pas répondre.
          </p>
        </div>
      </body>
    </html>
    """

    # ---------- Construction du message multipart ----------
    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to

    alt = MIMEMultipart("alternative")
    msg.attach(alt)

    # Partie texte (fallback) + HTML
    alt.attach(MIMEText(text_body, "plain", _charset="utf-8"))
    alt.attach(MIMEText(html_body, "html", _charset="utf-8"))

    # ---------- Logo inline ----------
    if logo_exists:
        try:
            with open(logo_path, "rb") as f:
                img = MIMEImage(f.read())
            img.add_header("Content-ID", "<itstorm_logo>")
            img.add_header("Content-Disposition", "inline", filename="itstorm_logo.png")
            msg.attach(img)
        except Exception as e:
            # On ne bloque pas l'envoi si le logo plante
            st.warning(f"Impossible de joindre le logo IT-STORM: {e}")

    # ---------- Envoi SMTP ----------
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
# CSS / UI Helpers
# =========================

def _inject_auth_css() -> None:
    """
    Injection CSS :
      - Style carte moderne
      - Animation de transition entre étapes (slide + zoom)
    """
    if st.session_state.get("_auth_css_injected"):
        return

    st.markdown(
        """
        <style>
        body {
            font-family: 'Inter', system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
        }

        @keyframes authCardStep {
            from {
                opacity: 0;
                transform: translateY(28px) scale(0.93);
            }
            to {
                opacity: 1;
                transform: translateY(0px) scale(1.0);
            }
        }

        .auth-card {
            background: #ffffff;
            padding: 35px 40px;
            border-radius: 18px;
            box-shadow: 0px 12px 28px rgba(15, 23, 42, 0.18);
            width: 420px;
            margin-left: auto;
            margin-right: auto;
            margin-top: 10px;
            margin-bottom: 20px;
            animation: authCardStep 0.4s cubic-bezier(0.22, 0.61, 0.36, 1);
        }

        .auth-title {
            font-size: 26px;
            font-weight: 700;
            text-align: center;
            margin-bottom: 6px;
        }

        .auth-subtitle {
            font-size: 13px;
            text-align: center;
            color: #6b7280;
            margin-bottom: 14px;
        }

        .auth-step {
            text-align: center;
            color: #6c757d;
            margin-bottom: 22px;
            font-size: 14px;
        }

        input[type="text"], input[type="password"] {
            border-radius: 10px !important;
            padding: 11px 12px !important;
            border: 1px solid #D0D7E2 !important;
            font-size: 15px !important;
        }

        input[type="text"]:focus, input[type="password"]:focus {
            border-color: #2563eb !important;
            box-shadow: 0 0 0 1px rgba(37, 99, 235, 0.15) !important;
        }

        .stButton > button {
            width: 100%;
            border-radius: 12px;
            padding: 11px 0;
            background: linear-gradient(90deg, #2563eb, #3b82f6);
            color: white;
            font-size: 15px;
            border: none;
            font-weight: 600;
            transition: 0.18s ease;
        }

        .stButton > button:hover {
            background: linear-gradient(90deg, #1d4ed8, #2563eb);
            transform: translateY(-1px);
            box-shadow: 0 8px 16px rgba(37, 99, 235, 0.25);
        }

        .stButton > button:active {
            transform: translateY(0px) scale(0.99);
            box-shadow: none;
        }

        .resend-btn button {
            background: #f1f5f9 !important;
            color: #475569 !important;
            border-radius: 10px !important;
            border: 1px solid #e2e8f0 !important;
            font-size: 13px !important;
        }

        .resend-btn button:hover {
            background: #e2e8f0 !important;
        }

        .captcha-box, .qr-box {
            background: #f8fafc;
            padding: 16px;
            border-radius: 14px;
            text-align: center;
            border: 1px solid #e2e8f0;
            margin-top: 8px;
            margin-bottom: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_auth_css_injected"] = True


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
            st.session_state["auth_just_logged_in"] = False
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

    _inject_auth_css()
    step = st.session_state.get("auth_step", 1)

    # Étape 1 : login + captcha
    if step == 1:
        st.markdown(
            """
            <div class="auth-card">
              <div class="auth-title">🔐 Accès StormCopilot</div>
              <div class="auth-subtitle">Connexion sécurisée avec authentification multi-facteurs</div>
              <div class="auth-step">Étape 1 sur 3 — Connexion + captcha</div>
            """,
            unsafe_allow_html=True,
        )

        _ensure_captcha()
        captcha_text = st.session_state.get("captcha_text", "ERROR")
        img_bytes = _generate_captcha_image(captcha_text)

        submitted = False
        user = ""
        pwd = ""
        captcha_input = ""

        with st.form("login_form_step1"):
            user = st.text_input(_t_auth("auth_user"))
            pwd = st.text_input(_t_auth("auth_password"), type="password")

            if img_bytes is not None:
                st.markdown("<div class='captcha-box'>", unsafe_allow_html=True)
                st.image(img_bytes, caption="Vérification anti-robot", width=260)
                st.markdown("</div>", unsafe_allow_html=True)

            captcha_label = _t_auth("auth_captcha_label")
            captcha_input = st.text_input(captcha_label)

            submitted = st.form_submit_button(_t_auth("auth_submit_login"))

        if submitted:
            with st.spinner("⏳ Vérification en cours…"):
                time.sleep(0.5)
                if not _check_captcha(captcha_input):
                    st.error(_t_auth("auth_captcha_error"))
                    _reset_captcha()
                else:
                    if _check_login_credentials(user, pwd):
                        st.session_state["auth_step"] = 2
                        st.markdown("</div>", unsafe_allow_html=True)
                        st.rerun()
                        return False
                    else:
                        st.error(_t_auth("auth_error_login"))
                        _reset_captcha()

        st.markdown("</div>", unsafe_allow_html=True)
        return False

    # Étape 2 : TOTP
    if step == 2:
        st.markdown(
            """
            <div class="auth-card">
              <div class="auth-title">🔐 Accès StormCopilot</div>
              <div class="auth-subtitle">Protection par code temporel</div>
              <div class="auth-step">Étape 2 sur 3 — Google Authenticator</div>
            """,
            unsafe_allow_html=True,
        )

        if not _is_totp_enabled():
            with st.spinner("⏳ Vérification en cours…"):
                time.sleep(0.4)
                _start_email_otp_flow()
            st.markdown("</div>", unsafe_allow_html=True)
            st.rerun()
            return False

        _render_totp_qr_forced()
        st.caption(_t_auth("auth_totp_info"))

        submitted_totp = False
        totp_input = ""

        with st.form("login_form_step2_totp"):
            totp_input = st.text_input("Code Google Authenticator")
            submitted_totp = st.form_submit_button(_t_auth("auth_submit_totp"))

        if submitted_totp:
            with st.spinner("⏳ Vérification en cours…"):
                time.sleep(0.5)
                if _check_totp_code(totp_input):
                    _start_email_otp_flow()
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.rerun()
                    return False
                else:
                    st.error(_t_auth("auth_error_totp"))

        st.markdown("</div>", unsafe_allow_html=True)
        return False

    # Étape 3 : code email
    if step == 3:
        st.markdown(
            """
            <div class="auth-card">
              <div class="auth-title">🔐 Accès StormCopilot</div>
              <div class="auth-subtitle">Dernière vérification avant l'accès complet</div>
              <div class="auth-step">Étape 3 sur 3 — Vérification email</div>
            """,
            unsafe_allow_html=True,
        )

        mail_to = os.getenv("SC_EMAIL_TO", "")
        if mail_to:
            st.caption(f"{_t_auth('auth_email_sent_to')} `{mail_to}`")
        else:
            st.caption(_t_auth("auth_email_sent"))

        col1, col2 = st.columns([2, 1])

        submitted_code = False
        code_input = ""

        with col1:
            with st.form("login_form_step3_email"):
                code_input = st.text_input(_t_auth("auth_email_code"))
                submitted_code = st.form_submit_button(_t_auth("auth_submit_code"))

        with col2:
            st.markdown("<div class='resend-btn'>", unsafe_allow_html=True)
            if st.button(_t_auth("auth_resend_code"), key="btn_resend_code"):
                with st.spinner("⏳ Envoi d'un nouveau code…"):
                    time.sleep(0.4)
                    _start_email_otp_flow()
                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)
                st.rerun()
                return False
            st.markdown("</div>", unsafe_allow_html=True)

        if submitted_code:
            with st.spinner("⏳ Vérification en cours…"):
                time.sleep(0.5)
                status = _check_email_code(code_input)

                if status == "ok":
                    st.session_state["is_authenticated"] = True
                    st.session_state["auth_step"] = 1
                    st.session_state["auth_just_logged_in"] = True
                    st.session_state.pop("email_otp", None)
                    st.session_state.pop("email_otp_expires_at", None)
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.rerun()
                    return False
                elif status == "expired":
                    st.error(_t_auth("auth_error_code_expired"))
                else:
                    st.error(_t_auth("auth_error_code"))

        st.markdown("</div>", unsafe_allow_html=True)
        return False

    st.session_state["auth_step"] = 1
    return False

# End of src/ui/sections/auth.py
