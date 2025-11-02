import os

CHROMA_DIR = os.getenv("CHROMA_DIR", "./data/chroma-consulting")
DATA_DIR = os.getenv("DATA_DIR", "./data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "consulting")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
