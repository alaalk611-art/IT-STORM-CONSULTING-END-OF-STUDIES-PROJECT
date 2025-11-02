from __future__ import annotations
import sys
import base64
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from streamlit_javascript import st_javascript

# --- Setup sys.path ---
ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / "tools"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if TOOLS.exists() and str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

# --- QA backend
try:
    from tools.qa_cli_pretty import answer_from_cli_backend
except Exception:
    def answer_from_cli_backend(q: str) -> str:
        return "⚠️ Backend QA introuvable (tools/qa_cli_pretty.py)."

def _init_state():
    st.session_state.setdefault("lang", "fr")

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

def render_chatbot():
    _init_state()
    lang = st.session_state.get("lang", "fr")
    placeholder = "Pose ta question..." if lang == "fr" else "Type your question..."

    st.markdown(f"""
<div id="chat-bubble">💬</div>
<div id="chat-window" style="display:none">
  <div class="chat-header">
    <div class="title">{_logo_html()}StormCopilot</div>
    <div class="close-btn">✖</div>
  </div>
  <div class="chat-body" id="chat-body"></div>
  <div class="chat-input">
    <input id="chat-input-field" placeholder='{placeholder}'/>
    <button id="chat-send-btn">▶</button>
  </div>
</div>

<style>
#chat-bubble {{ position:fixed; bottom:20px; right:20px; background:#0b285a; color:#fff;
  width:60px; height:60px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:28px; cursor:pointer; box-shadow:0 8px 16px rgba(0,0,0,.3);
  z-index:9999; transition:transform .2s; }}
#chat-bubble:hover {{ transform:scale(1.08); }}
#chat-window {{ position:fixed; bottom:90px; right:20px; width:90vw; max-width:360px; background:#fff;
  border:1px solid #cfd7e6; border-radius:14px; box-shadow:0 10px 28px rgba(0,0,0,.35);
  overflow:hidden; z-index:9998; animation:fadeIn .25s ease-out; }}
@keyframes fadeIn {{ from {{opacity:0; transform:translateY(10px);}} to {{opacity:1; transform:translateY(0);}} }}
.chat-header {{ background:#0b285a;color:#fff;padding:10px;display:flex;justify-content:space-between;
  align-items:center;font-weight:700 }}
.chat-body {{ max-height:280px;overflow-y:auto;padding:10px;background:#f9fafb;font-size:14px;color:#0b1220 }}
.chat-input {{ display:flex;border-top:1px solid #e6ebf5 }}
#chat-input-field {{ flex:1;padding:8px;border:none;outline:none;font-size:14px }}
#chat-send-btn {{ background:#0b285a;color:#fff;border:none;width:52px;cursor:pointer }}
.close-btn {{ cursor:pointer }}
@media screen and (max-width:480px) {{ #chat-window {{ right:10px; width:95vw; }} #chat-bubble {{ right:10px; bottom:15px; }} }}
</style>
""", unsafe_allow_html=True)

    input_val = st_javascript("""
    new Promise((resolve) => {
      (window.parent || window).addEventListener("message", (event) => {
        if (event.data && event.data.type === "streamlit:setComponentValue") {
          resolve(event.data.value);
        }
      }, { once: true });
    })
    """, key="chat_input_event")

    if input_val:
        try:
            result = answer_from_cli_backend(str(input_val)).strip()
        except Exception as e:
            result = f"⚠️ Erreur backend: {e}"

        if result.startswith("SUGGEST:"):
            lines = result.splitlines()
            sug = {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in lines if ":" in l)}
            q = sug.get("SUGGEST", "")
            a = sug.get("IF_YES_ANSWER", "Je ne sais pas")
            src = sug.get("SOURCE", "inconnu")
            formatted = f"Tu veux dire : « {q} » ?\n\n👉 Réponds 'o' (oui) ou 'n' (non).\n\n(source : {src})"
        else:
            formatted = result

        b64 = base64.b64encode(formatted.encode("utf-8")).decode("ascii")
        st_javascript(f"""
        const b64="{b64}";
        const decoded = decodeURIComponent(escape(window.atob(b64)));
        (window.parent || window).streamlitChatAnswer = decoded;
        """, key=f"resp_{abs(hash(b64))}")

    components.html("""
    <script>
    (function(){
      const bubble = window.parent.document.getElementById('chat-bubble');
      const win    = window.parent.document.getElementById('chat-window');
      const close  = win ? win.querySelector('.close-btn') : null;
      const send   = window.parent.document.getElementById('chat-send-btn');
      const input  = window.parent.document.getElementById('chat-input-field');
      const body   = window.parent.document.getElementById('chat-body');

      function append(text, who){
        const div=document.createElement('div');
        div.textContent=(who==='user'?'👤 ':'🤖 ')+text;
        body.appendChild(div);
        body.scrollTop=body.scrollHeight;
      }

      if(bubble&&win){
        bubble.addEventListener('click',()=>{win.style.display=(win.style.display==='block'?'none':'block');});
      }
      if(close) close.addEventListener('click',()=>{win.style.display='none';});

      async function waitForAnswer(maxMs=1000, step=200){
        const deadline=Date.now()+maxMs;
        return new Promise((resolve)=>{
          const timer=setInterval(()=>{
            if(window.parent.streamlitChatAnswer){
              const ans=window.parent.streamlitChatAnswer;
              window.parent.streamlitChatAnswer=null;
              clearInterval(timer); resolve(ans);
            } else if(Date.now()>deadline){
              clearInterval(timer); resolve('⏳ Pas de réponse.');
            }
          }, step);
        });
      }

      async function sendMessage(){
        const msg=(input.value||'').trim();
        if(!msg) return;
        append(msg,'user'); input.value='';
        window.parent.streamlitChatAnswer=null;
        window.parent.postMessage({type:'streamlit:setComponentValue', value:msg}, '*');
        const resp=await waitForAnswer();
        append(resp,'bot');
      }

      if(send&&input){
        send.onclick=sendMessage;
        input.addEventListener('keydown',e=>{
          if(e.key==='Enter'){e.preventDefault();sendMessage();}
        });
      }
    })();
    </script>
    """, height=0)
