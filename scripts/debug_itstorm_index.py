# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from src.rag_brain import debug_has_file, debug_list_sources

if __name__ == "__main__":
    print("Présence itstorm.txt :", debug_has_file("itstorm.txt"))
    print("\nExtrait des sources visibles :")
    for s in debug_list_sources(30):
        print(" -", s)
