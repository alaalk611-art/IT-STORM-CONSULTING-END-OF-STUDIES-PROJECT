
# ---------------------------
import streamlit as st
import concurrent.futures
from tools.qa_cli_pretty import answer_from_cli_backend
import base64
from pathlib import Path
import streamlit.components.v1 as components
from streamlit_javascript import st_javascript

def render_chatbot():
    # Init state
    if "copilot_messages" not in st.session_state:
        st.session_state.copilot_messages = []
    if "copilot_suggestions" not in st.session_state:
        st.session_state.copilot_suggestions = []
    if "copilot_suggestion_index" not in st.session_state:
        st.session_state.copilot_suggestion_index = 0
    if "copilot_awaiting" not in st.session_state:
        st.session_state.copilot_awaiting = False

    def _b64(p: Path) -> str:
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _logo_html() -> str:
        for p in (
            Path("src/ui/assets/itstorm.png"),
            Path(__file__).resolve().parents[1] / "assets" / "itstorm.png",
        ):
            if p.exists():
                return f'<img src="data:image/png;base64,{_b64(p)}" width="22" style="margin-right:6px;"/>'
        return "🤖"

    # Affichage historique
    st.markdown("<div class='copilot-chat'>", unsafe_allow_html=True)
    st.header("StormCopilot")

    for msg in st.session_state.copilot_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Suggestions Oui / Non
    if st.session_state.copilot_awaiting:
        suggestions = st.session_state.copilot_suggestions
        i = st.session_state.copilot_suggestion_index
        if i < len(suggestions):
            suggestion = suggestions[i]
            sug_text = suggestion.get("SUGGEST", "")
            col1, col2 = st.columns(2)
            if col1.button("Oui", key="sug_yes"):
                st.session_state.copilot_messages.append({"role": "user", "content": "Oui"})
                with st.chat_message("user"):
                    st.markdown("Oui")
                answer = suggestion.get("IF_YES_ANSWER", "Je ne sais pas")
                source = suggestion.get("SOURCE", "")
                full = f"{answer}\n\nSource : ({source})" if source else answer
                st.session_state.copilot_messages.append({"role": "assistant", "content": full})
                with st.chat_message("assistant"):
                    st.markdown(full)
                st.session_state.copilot_awaiting = False
                st.session_state.copilot_suggestions = []
                st.session_state.copilot_suggestion_index = 0
            elif col2.button("Non", key="sug_no"):
                st.session_state.copilot_messages.append({"role": "user", "content": "Non"})
                with st.chat_message("user"):
                    st.markdown("Non")
                st.session_state.copilot_suggestion_index += 1
                if st.session_state.copilot_suggestion_index < len(suggestions):
                    next_sug = suggestions[st.session_state.copilot_suggestion_index]
                    msg = f"Suggestion : {next_sug.get('SUGGEST', '')} (Oui/Non)"
                    st.session_state.copilot_messages.append({"role": "assistant", "content": msg})
                    with st.chat_message("assistant"):
                        st.markdown(msg)
                else:
                    msg = "Aucune autre suggestion."
                    st.session_state.copilot_messages.append({"role": "assistant", "content": msg})
                    with st.chat_message("assistant"):
                        st.markdown(f"**{msg}**")
                    st.session_state.copilot_awaiting = False

    # Entrée utilisateur
    if not st.session_state.copilot_awaiting:
        q = st.chat_input("Pose ta question...")
        if q:
            st.session_state.copilot_messages.append({"role": "user", "content": q})
            with st.chat_message("user"):
                st.markdown(q)
            with st.spinner("Réflexion en cours..."):
                def get_answer():
                    return answer_from_cli_backend(q)
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(get_answer)
                    try:
                        result = future.result(timeout=15)
                    except concurrent.futures.TimeoutError:
                        st.session_state.copilot_messages.append({"role": "assistant", "content": "⏳ Pas de réponse."})
                        with st.chat_message("assistant"):
                            st.markdown("⏳ Pas de réponse.")
                        st.stop()
            if result.startswith("SUGGEST:"):
                lines = result.strip().splitlines()
                parsed = {}
                for line in lines:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        parsed[key.strip()] = val.strip()
                st.session_state.copilot_suggestions = [parsed]
                st.session_state.copilot_suggestion_index = 0
                st.session_state.copilot_awaiting = True
                sug = parsed.get("SUGGEST", "")
                msg = f"Suggestion : {sug} (Oui/Non)"
                st.session_state.copilot_messages.append({"role": "assistant", "content": msg})
                with st.chat_message("assistant"):
                    st.markdown(msg)
            else:
                st.session_state.copilot_messages.append({"role": "assistant", "content": result})
                with st.chat_message("assistant"):
                    st.markdown(result)

    st.markdown("</div>", unsafe_allow_html=True)