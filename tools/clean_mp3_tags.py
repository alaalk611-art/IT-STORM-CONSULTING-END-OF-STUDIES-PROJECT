# clean_mp3_tags.py
from mutagen.mp3 import MP3
import sys
import os

def clean_tags(path):
    if not os.path.exists(path):
        print(f"❌ Fichier introuvable : {path}")
        return

    print(f"🔍 Nettoyage des tags ID3 du fichier : {path}")

    audio = MP3(path)

    print("🧼 Suppression des tags ID3 (lyrics, commentaires, sous-titres, etc.)...")
    audio.delete()   # supprime TOUS les tags ID3 (USLT, COMM, TXXX…)

    audio.save()

    print("✅ Tags supprimés avec succès !")
    print("🔥 Le fichier est maintenant propre, prêt pour Whisper.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clean_mp3_tags.py <chemin_du_fichier_mp3>")
    else:
        clean_tags(sys.argv[1])
        ####
