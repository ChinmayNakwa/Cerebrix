# Cerebrix 🧠🤖

[![Python Version](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Framework](https://img.shields.io/badge/Framework-LangGraph-blueviolet)](https://langchain.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Your AI teaching assistant for YouTube courses, combining video lectures, textbooks, and Socratic tutoring in one conversational interface.

<img width="1899" height="1045" alt="image" src="https://github.com/user-attachments/assets/ac805f4c-96a6-4dd9-a65d-b9bd51584bfb" />

<img width="1914" height="1041" alt="image" src="https://github.com/user-attachments/assets/949e91ce-d789-4ed4-b4f7-db40bb0aaf78" />


---

## 📖 Description

Cerebrix transforms passive video learning into an interactive educational experience. This AI-powered teaching assistant can answer questions, explain concepts, and provide Socratic guidance for any YouTube course with accompanying materials.

The current deployment focuses on Stanford's CS109 (Probability for Computer Scientists), but the architecture is course-agnostic and can be adapted to any subject.

**Why Cerebrix?**

*   **Fills the Learning Gap:** Transforms one-way video lectures into interactive conversations.
*   **Learn By Doing:** Receive guided hints on problems rather than direct answers.
*   **Course-Agnostic:** Adaptable architecture supports any YouTube course.
*   **Always Available:** 24/7 access to course-specific tutoring without waiting for office hours.
*   **Multi-Modal Understanding:** Processes both text and images for comprehensive support.

---

## 💡 Motivation

While studying Stanford's CS109 on YouTube, I encountered a common frustration: there was no way to discuss problems or get guidance when attempting exercises. As someone passionate about understanding the mathematics behind AI, I wanted a TA or study companion to support this journey, so I built one.

This project emerged from that need, creating an intelligent assistant that any self-directed learner can use to enhance their online education experience.

---


## Features

-   **Multi-Modal Knowledge Base:** Ingests the CS109 course book and all 29 lectures of the YouTube playlist, including formulas, slides and keyframes.
-   **Hybrid Retrieval:** Searches with both `pgvector` similarity and Postgres full-text search, fuses the two rankings and narrows to a lecture or page when the question names one.
-   **Concept Graph:** Concepts, definitions, theorems and formulas extracted from the book and lectures are linked in a graph, so answers can pull in closely related material.
-   **Cited Sources:** Every answer lists where it came from, with book page ranges and lecture timestamps that link to the exact moment in the video.
-   **Socratic Tutoring:** When a user submits their work (via text or image), the agent analyzes their approach and provides guiding hints rather than direct answers. Questions about concepts and definitions get a direct answer.
-   **Self-Review:** Each answer is checked against the tutor's rules before it is sent, and regenerated once if it falls short.
-   **Voice:** Questions can be spoken and answers read aloud, both with models that run locally.
-   **Maths Rendering:** Answers render LaTeX with KaTeX.
-   **Conversational Memory:** Each chat is stored in Postgres, so follow-up questions keep their context.

## Project Architecture

-   **Backend:** A `FastAPI` server running a `LangGraph` agent, traced in `LangSmith`.
-   **Frontend:** A `Next.js` app with `Ant Design`, a chat page, and an about page with interactive `React Flow` diagrams of how Cerebrix works.
-   **Database:** `PostgreSQL` with `pgvector` for the chunk embeddings, full-text search, the concept graph and chat history (LangGraph checkpoints).
-   **Image Hosting:** `Cloudinary` for storing page images and video keyframes.
-   **LLMs:** `Ollama Cloud`, with `gpt-oss:120b` for reasoning and answers and `gemma4:31b` for reading images.
-   **Speech:** Local `faster-whisper` for voice questions and `Kokoro` for text-to-speech.
-   **Data Ingestion:** A staged Python pipeline (`backend/ingestion`) using `Docling` and `PyMuPDF` for the textbook, YouTube captions, `yt-dlp` and `ffmpeg` keyframes for the lectures, Ollama Cloud vision for formulas and slides, and `bge-base-en-v1.5` embeddings.

### The Agent Graph

This is the tutor's LangGraph graph, the same one LangSmith Studio shows. Solid arrows always run; dotted arrows are conditional.

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([__start__]):::first
	extract_filters(extract_filters)
	route_question(route_question)
	ask_clarification_question(ask_clarification_question)
	simple_rag(simple_rag)
	transcribe_image(transcribe_image)
	critique_work(critique_work)
	retrieve_context(retrieve_context)
	generate_socratic_response(generate_socratic_response)
	reflect_on_answer(reflect_on_answer)
	finalize_history(finalize_history)
	__end__([__end__]):::last
	__start__ --> extract_filters;
	ask_clarification_question -.-> __end__;
	ask_clarification_question -. &nbsp;finalize&nbsp; .-> finalize_history;
	ask_clarification_question -.-> reflect_on_answer;
	critique_work -.-> generate_socratic_response;
	critique_work -.-> retrieve_context;
	extract_filters --> route_question;
	generate_socratic_response -.-> __end__;
	generate_socratic_response -. &nbsp;finalize&nbsp; .-> finalize_history;
	generate_socratic_response -.-> reflect_on_answer;
	reflect_on_answer -.-> __end__;
	reflect_on_answer -. &nbsp;finalize&nbsp; .-> finalize_history;
	reflect_on_answer -.-> generate_socratic_response;
	reflect_on_answer -.-> simple_rag;
	retrieve_context --> generate_socratic_response;
	route_question -.-> ask_clarification_question;
	route_question -.-> simple_rag;
	route_question -.-> transcribe_image;
	simple_rag -.-> __end__;
	simple_rag -. &nbsp;finalize&nbsp; .-> finalize_history;
	simple_rag -.-> reflect_on_answer;
	transcribe_image --> critique_work;
	finalize_history --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

| Node | What it does |
|---|---|
| `extract_filters` | Pulls a lecture number or book page out of the question, to narrow the search. |
| `route_question` | Sends questions about concepts to `simple_rag`, submitted work (or any image) to `transcribe_image`, and unclear messages to `ask_clarification_question`. Later turns are routed with the whole conversation in view. |
| `simple_rag` | Retrieves the top 5 passages and answers from them alone. |
| `transcribe_image` | Reads a photo of the student's work with the vision model. |
| `critique_work` | Finds where the student's approach goes wrong and decides whether course material is needed. |
| `retrieve_context` | Retrieves the top 3 passages for the critique. |
| `generate_socratic_response` | Writes a guiding hint instead of the full solution. |
| `ask_clarification_question` | Asks the student what they mean. |
| `reflect_on_answer` | Checks the answer against the tutor's rules and sends it back for one regeneration if it fails. |
| `finalize_history` | Saves the approved answer to the chat history. |

Clarifying questions skip the review, and error replies end the run without being saved.

To open the graph in LangSmith Studio and step through runs, run `langgraph dev` from the repository root (it reads `langgraph.json`). To regenerate the diagram above after changing the graph:

```bash
python -c "from backend.core.rag.agent import workflow; print(workflow.compile().get_graph().draw_mermaid())"
```

---

## 🚀 Getting Started

Follow these steps to set up and run Cerebrix on your local machine.

### 1. Prerequisites

-   [Anaconda or Miniconda](https://www.anaconda.com/download) installed.
-   [Docker](https://www.docker.com/products/docker-desktop/) for the local PostgreSQL database.
-   [Node.js](https://nodejs.org/) for the frontend.
-   Access keys for:
    -   Ollama Cloud
    -   Cloudinary
    -   LangSmith (the backend needs a key and always sends traces there)

### 2. Environment Setup

This project uses `conda` to manage its complex dependencies.

```bash
# Clone the repository
git clone https://github.com/ChinmayNakwa/Maths-TA.git
cd Maths-TA

# Create and activate the conda environment
conda create --name cerebrix python=3.12
conda activate cerebrix

# Install ffmpeg (used by the video ingestion stage)
conda install -c conda-forge ffmpeg

# Install Python packages using pip
pip install -r backend/requirements.txt

```

### 3. Configuration

Copy `.env.example` to `.env` and fill in the keys. `LANGSMITH_PROJECT` names the LangSmith project the traces go to. With the database from the next step, `POSTGRES_DB_URL` is `postgresql://mathsta:mathsta@127.0.0.1:5435/mathsta` (use `127.0.0.1`, not `localhost`). Also set `PDF_PATH` to the textbook PDF and `VIDEO_DIR` to a folder holding the lecture videos as `.mp4` files named after their YouTube titles.

### 4. Database

```bash
docker compose up -d
python -m backend.database.schema
```

### 5. Ingest the Course

Each stage caches its results in `.ingest_cache/`, so a rerun only redoes what changed.

```bash
python -m backend.ingestion.pdf_stage                 # textbook pages with Docling
python -m backend.ingestion.pdf_vision                # formulas Docling could not read
python -m backend.ingestion.video_stage               # captions and slides for each lecture
python -m backend.ingestion.chunk_stage --book --lectures
python -m backend.ingestion.ontology_stage            # concept graph

# Optional: measure retrieval on the golden question set
python -m backend.core.rag.evaluate
```

### 6. Run

```bash
# Backend on port 8000 (on Windows, add --loop asyncio:SelectorEventLoop: async psycopg cannot use the default Proactor loop)
uvicorn backend.app:app --port 8000

# Frontend on port 3000 (proxies /api/py to API_URL, default http://127.0.0.1:8000)
cd client
npm install
npm run dev
```

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

---

## 🙏 Acknowledgments

*   Stanford CS109 course materials
*   LangChain and LangGraph teams
*   Ollama
*   The open-source community

---

## 📧 Contact

For questions or feedback, please open an issue on GitHub or reach out to `29chinmaynakwa@gmail.com`.

---

> **⚠️ Important Note:** When replicating this project for other courses, be mindful of copyright and fair use policies for course materials. Ensure you have appropriate permissions to process and use the content.

## ⚖️ Copyright & Fair Use Notice

This project is designed as an educational tool to enhance learning from publicly available course materials. We believe this constitutes fair use under copyright law for the following reasons:

-   **Educational Purpose**: Non-commercial teaching aid for self-directed learners
-   **Transformative Use**: Creates an interactive tutoring interface not present in original materials
-   **Attribution**: All content is attributed to original creators with links to source materials
-   **No Market Harm**: Designed to complement, not replace, the original course experience

**All course content remains the property of its original creators.** This project:

-   Does not claim ownership of any course materials
-   Is not monetized in any way
-   Can be removed upon request from content owners

If you are a content owner and have concerns about this project's use of your materials, please contact `29chinmaynakwa@gmail.com` and we will respond promptly.

**For other users replicating this project**: Please ensure you have appropriate permissions for any copyrighted materials you process. Fair use determinations are made on a case-by-case basis.

