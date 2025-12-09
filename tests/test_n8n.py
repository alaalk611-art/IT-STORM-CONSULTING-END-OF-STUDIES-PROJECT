import streamlit as st
import requests

URL = "http://localhost:5678/webhook/stormcopilot-test"

def send_to_n8n(name, message):
    payload = {"name": name, "message": message}
    r = requests.post(URL, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

st.title("Test Streamlit → n8n")

name = st.text_input("Nom", "Ala")
msg = st.text_input("Message", "Ceci est un test 🧪")

if st.button("Envoyer"):
    try:
        response = send_to_n8n(name, msg)
        st.subheader("Réponse de n8n")
        st.json(response)
    except Exception as e:
        st.error(f"Erreur lors de l'appel à n8n : {e}")
