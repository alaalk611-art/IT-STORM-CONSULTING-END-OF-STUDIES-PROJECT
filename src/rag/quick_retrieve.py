# src/rag/quick_retrieve.py
import os

import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
DB_DIR = os.getenv("CHROMA_DIR", "./data/chroma-consulting")
EMB_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
COLL_NAME = os.getenv("CHROMA_COLLECTION", "consulting")

client = chromadb.Client(Settings(persist_directory=DB_DIR, is_persistent=True))
coll = client.get_or_create_collection(COLL_NAME)
