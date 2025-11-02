import os


def get_chroma_dir() -> str:
    return os.getenv("CHROMA_DIR", "./data/chroma-consulting")


def get_data_dir() -> str:
    return os.getenv("DATA_DIR", "./data")
