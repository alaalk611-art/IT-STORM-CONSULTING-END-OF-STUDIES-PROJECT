import os
import chromadb
from chromadb.config import Settings
from dotenv import load_dotenv
load_dotenv()


DB_PATH = os.getenv("CHROMA_DB_DIR") or os.getenv("VECTOR_DB_PATH") or "./vectors"
COLL   = os.getenv("VECTOR_COLLECTION", "consulting")

client = chromadb.PersistentClient(path=DB_PATH, settings=Settings(anonymized_telemetry=False))
col = client.get_or_create_collection(name=COLL)

print("DB_PATH =", DB_PATH)
print("COLLECTION =", COLL)
print("COUNT =", col.count())
