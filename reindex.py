from dotenv import load_dotenv
load_dotenv()

from src import rag_brain as rb

FILES = [
    (
        r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\raw\itstorm_rag_global.txt",
        "itstorm_rag_global.txt"
    ),
    (
        r"C:\Users\ALA BEN LAKHAL\Desktop\intelligent_copilot IT-STORM\data\raw\itstorm_site.txt",
        "itstorm_site.txt"
    ),
]

for fp, basename in FILES:
    print(f"Indexing {basename}")
    res = rb.reindex_txt_file(
        filepath=fp,
        source_basename=basename,
        max_words=220
    )
    print(res)
