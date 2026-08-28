import os
from huggingface_hub import hf_hub_download

# Cache Hugging Face sur le disque D (modifiable selon ta machine).
os.environ.setdefault("HF_HOME", "D:/huggingface_cache")

# Token Hugging Face : LU DEPUIS L'ENVIRONNEMENT — jamais codé en dur.
#   PowerShell :  $env:HF_TOKEN = "hf_xxx"
#   bash       :  export HF_TOKEN=hf_xxx
# (ou via le fichier .env à la racine, cf. .env.example.txt)
HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    raise SystemExit(
        "Variable d'environnement HF_TOKEN manquante. "
        "Définis-la avant de lancer ce script (voir .env.example.txt)."
    )

repo_id = "Buraaq/quran-audio-text-dataset"
filename = "quran_audio_data.tar.gz"

print("--------------------------------------------------")
print("Connexion sécurisée établie avec Hugging Face.")
print("Téléchargement du fichier de 36.1 GB en cours...")
print("Note : Si le téléchargement s'interrompt, relance")
print("simplement ce script, il reprendra là où il s'est arrêté.")
print("--------------------------------------------------")

try:
    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        repo_type="dataset",
        token=HF_TOKEN,
        local_dir="D:/Quran_App_Project/Data",
        local_dir_use_symlinks=True,
    )
    print(f"\n Succès ! Le fichier brut est enregistré ici : {local_path}")
except Exception as e:
    print(f"\n Une erreur est survenue : {e}")
