# scripts/reset_chroma_itstorm.py

from src.rag_brain import (
    get_engine,
    reindex_txt_file,
    ensure_qa_indexed,
    debug_list_sources,
)

def main():
    eng = get_engine()

    print("🧹 Suppression de TOUTES les entrées de la collection Chroma...")
    try:
        eng.col.delete(where={})  # vide toute la collection
        print("✅ Collection vidée.")
    except Exception as e:
        print(f"⚠️ Erreur lors du delete global: {e}")

    print("\n📥 Réindexation de itstorm.txt ...")
    res1 = reindex_txt_file(
        filepath=r"data/raw/itstorm.txt",
        source_basename="itstorm.txt",
        max_words=220,
    )
    print("   ->", res1)

    print("\n📥 Réindexation de exemple_rag_itstorm.txt ...")
    res2 = reindex_txt_file(
        filepath=r"data/raw/exemple_rag_itstorm.txt",
        source_basename="exemple_rag_itstorm.txt",
        max_words=220,
    )
    print("   ->", res2)

    print("\n📥 Réindexation de it_storm_1000_QA.txt ...")
    res3 = ensure_qa_indexed([
        r"data/raw/it_storm_1000_QA.txt",
    ])
    print("   ->", res3)

    print("\n🔎 Sources présentes dans Chroma après reset :")
    print(debug_list_sources(80))

if __name__ == "__main__":
    main()
