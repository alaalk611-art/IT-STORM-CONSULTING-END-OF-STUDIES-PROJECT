# 🌩️ StormCopilot

**StormCopilot** est une plateforme d’assistance intelligente pour le **conseil et l’aide à la décision**, combinant **IA générative, RAG, automatisation de workflows et MLOps**.

La plateforme transforme **documents, données et signaux du marché** en **insights exploitables et livrables professionnels automatisés**.

---

# 🚀 Fonctionnalités principales

StormCopilot propose plusieurs modules d’intelligence augmentée :

### 🧠 Chat IA contextualisé (RAG)
- Analyse de documents internes
- Recherche sémantique dans une base vectorielle
- Réponses contextualisées avec LLM

### 📄 Génération automatique de livrables
Production automatique de :

- Rapports **PDF**
- Présentations **PowerPoint**
- Documents **DOCX**

### 📊 Veille intelligente
Analyse automatique de :

- tendances technologiques
- signaux marché
- innovations IA

### 🔁 Automatisation de workflows
Automatisation complète via **n8n** :

- pipelines de veille
- génération de rapports
- orchestrations data

### 📈 Gouvernance des modèles (MLOps)
Suivi et monitoring des modèles avec :

- **MLflow**
- suivi des performances
- gestion des expérimentations

---

## 🧱 Architecture du système

StormCopilot repose sur une architecture modulaire combinant plusieurs technologies IA modernes :

```
Users
 │
 ▼
Streamlit Interface
 │
 ▼
FastAPI Backend
 │
 ├── RAG Engine
 │   ├── Document ingestion
 │   ├── Chunking
 │   ├── Embeddings
 │   └── Vector Search (ChromaDB)
 │
 ├── LLM Manager
 │   └── Ollama (Mistral / Llama)
 │
 ├── Document Generator
 │   ├── DOCX
 │   ├── PPTX
 │   └── PDF
 │
 └── Automation Layer
     └── n8n workflows

Monitoring
 └── MLflow
```

---

## 📁 Structure du projet

```
storm_copilot/
│
├── data/                # Données brutes, intermédiaires et traitées
├── docs/                # Documentation du projet
├── mlops_metrics/       # Métriques et monitoring
├── mlruns/              # Expérimentations MLflow
├── models/              # Modèles IA
├── out/                 # Livrables générés
├── scripts/             # Scripts utilitaires
├── vectors/             # Base vectorielle (ChromaDB)
│
├── src/
│   ├── api/             # Points d’entrée API
│   ├── automation/      # Workflows n8n
│   ├── config/          # Configuration globale
│   ├── data_tech_watch/ # Veille technologique
│   ├── embeddings/      # Génération d’embeddings
│   ├── generation/      # DOCX / PPTX / PDF
│   ├── indexing/        # Indexation vectorielle
│   ├── ingestion/       # Extraction & prétraitement
│   ├── llm/             # Gestion des LLM locaux
│   ├── mlops/           # MLOps & monitoring
│   ├── n8n/             # Orchestration
│   ├── rag/             # Pipelines RAG
│   └── ui/              # Interface Streamlit
│
├── docker-compose.yml
├── requirements.txt
└── README.md
```

# 🛠️ Stack technique

StormCopilot combine plusieurs technologies modernes :

### Langages
- Python

### IA & NLP
- LangChain
- Transformers
- Ollama
- Mistral / Llama

### Data & vector search
- ChromaDB
- embeddings HuggingFace

### Backend
- FastAPI

### Interface utilisateur
- Streamlit

### Automatisation
- n8n

### MLOps
- MLflow

### Conteneurisation
- Docker
- Docker Compose

---
