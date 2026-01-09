🌩️ Storm Copilot
GenAI · Automation · n8n · Market Intelligence · MLOps

Storm Copilot est une plateforme d’IA conçue pour le conseil et l’aide à la décision, combinant IA générative, RAG, automatisation de workflows, veille intelligente et MLOps.

Elle transforme documents, données et signaux marché en insights actionnables et livrables professionnels automatisés.

🚀 What it does

🧠 Chat IA contextualisé (RAG)

📤 Ingestion & indexation documentaire

🧾 Génération automatique de rapports (PDF, DOCX, PPTX)

🔁 Orchestration de workflows avec n8n

📊 Veille marché & technologique augmentée par l’IA

📈 Suivi et gouvernance des modèles (MLOps)

🛠️ Tech Stack

Python · Streamlit · LangChain · ChromaDB · Ollama · n8n · MLflow

🎯 Built for

Consulting · Knowledge Management · Market Intelligence · GenAI Automation

📁 Project Structure
storm_copilot/
├─ data/                    # Données brutes, intermédiaires et traitées
├─ docs/                    # Documentation projet
├─ mlops_metrics/           # Métriques de suivi et monitoring
├─ mlruns/                  # Expérimentations MLflow
├─ models/                  # Modèles entraînés ou utilisés
├─ out/                     # Livrables générés (PDF, DOCX, PPTX)
├─ outputs/                 # Sorties intermédiaires et exports
├─ public/                  # Assets publics (images, logos, etc.)
├─ scripts/                 # Scripts utilitaires (setup, run, ingestion)
├─ tests/                   # Tests unitaires et fonctionnels
├─ tools/                   # Outils internes
├─ vectors/                 # Base vectorielle persistée (ChromaDB)
│
└─ src/
   ├─ api/                  # Points d’entrée API
   ├─ automation/           # Automatisation et intégration des workflows n8n
   ├─ config/               # Configuration globale (settings, chemins)
   ├─ data_tech_watch/      # Données de veille technologique
   ├─ embeddings/           # Génération et gestion des embeddings
   ├─ generation/           # Génération de livrables (DOCX, PPTX, PDF)
   ├─ indexing/             # Indexation et stockage vectoriel
   ├─ ingestion/            # Extraction texte et prétraitements
   ├─ llm/                  # Gestion des modèles de langage locaux
   ├─ mlops/                # Suivi, métriques et gouvernance des modèles
   ├─ n8n/                  # Définitions et connexions d’orchestration
   ├─ rag/                  # Pipelines RAG (retrieval + génération)
   ├─ rag_en/               # Variantes RAG multilingues
   ├─ ui/                   # Interface Streamlit (tabs, sections)
   ├─ utils/                # Helpers et outils transverses
   └─ app.py                # Point d’entrée principal de l’application
