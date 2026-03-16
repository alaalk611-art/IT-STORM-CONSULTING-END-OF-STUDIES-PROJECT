🌩️ Storm Copilot  
GenAI · Automation · n8n · Market Intelligence · MLOps  

Storm Copilot est une plateforme d’IA conçue pour le conseil et l’aide à la décision, combinant IA générative, RAG, automatisation de workflows, veille intelligente et MLOps.

Elle transforme documents, données et signaux marché en insights actionnables et livrables professionnels automatisés.

---

---

## 🎬 Demo

### AI Assistant Demo

<video src="demo/IA_demo.mp4" controls width="800"></video>

Voice-enabled assistant powered by RAG, local LLMs and document intelligence.

---

### n8n Automation Demo

<video src="demo/N8N_demo.mp4" controls width="800"></video>

Workflow orchestration and automation pipelines using n8n.

---


🚀 What it does

🧠 Chat IA contextualisé (RAG)  
📤 Ingestion & indexation documentaire  
🧾 Génération automatique de rapports (PDF, DOCX, PPTX)  
🔁 Orchestration de workflows avec n8n  
📊 Veille marché & technologique augmentée par l’IA  
📈 Suivi et gouvernance des modèles (MLOps)

---

🛠️ Tech Stack

Python · Streamlit · LangChain · ChromaDB · Ollama · n8n · MLflow

---

🎯 Built for

Consulting · Knowledge Management · Market Intelligence · GenAI Automation

---

📁 Project Structure

storm_copilot/
├─ data/                    # Données brutes, intermédiaires et traitées  
├─ docs/                    # Documentation projet  
├─ mlops_metrics/           # Métriques et monitoring  
├─ mlruns/                  # Expérimentations MLflow  
├─ models/                  # Modèles IA  
├─ out/                     # Livrables générés  
├─ scripts/                 # Scripts utilitaires  
├─ vectors/                 # Base vectorielle (ChromaDB)  
│  
└─ src/
   ├─ api/                  # Points d’entrée API  
   ├─ automation/           # Workflows n8n  
   ├─ config/               # Configuration globale  
   ├─ data_tech_watch/      # Veille technologique  
   ├─ embeddings/           # Embeddings  
   ├─ generation/           # DOCX / PPTX / PDF  
   ├─ indexing/             # Indexation vectorielle  
   ├─ ingestion/            # Extraction & prétraitement  
   ├─ llm/                  # LLM locaux  
   ├─ mlops/                # MLOps & monitoring  
   ├─ n8n/                  # Orchestration  
   ├─ rag/                  # Pipelines RAG  
   ├─ ui/                   # Interface Streamlit  
   └─ app.py                # Entrée principale
