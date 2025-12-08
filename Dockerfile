FROM python:3.11-slim

# ==========
# 1) Env de base
# ==========
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ==========
# 2) Dépendances système (ffmpeg pour voice, build-essential pour certaines libs)
# ==========
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ==========
# 3) Dossier de travail
# ==========
WORKDIR /app

# ==========
# 4) Install dépendances Python
# ==========
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# ==========
# 5) Copie du projet
# ==========
COPY . .

# S'assure que les dossiers existent
RUN mkdir -p /app/data /app/vectors

# ==========
# 6) Variables d'environnement internes au conteneur
#    (écrasent les chemins Windows)
# ==========
ENV DATA_DIR=/app/data \
    CHROMA_DB_DIR=/app/vectors \
    VECTOR_DB_PATH=/app/vectors \
    HF_HUB_OFFLINE=1 \
    HF_LOCAL_ONLY=true

# (Optionnel) si tu veux être sûr que le backend d'embedding est bien FastEmbed
ENV RAG_EMBED_BACKEND=fastembed

# Ports exposés :
# 8001 = FastAPI / Uvicorn
# 8501 = UI Streamlit
EXPOSE 8001 8501

# ==========
# 7) Commande de lancement :
#    - lance FastAPI (uvicorn)
#    - puis Streamlit dans le même conteneur
# ==========
CMD ["bash", "-c", "python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8001 & streamlit run src/ui/app.py --server.port=8501 --server.address=0.0.0.0"]
