import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
from agent.ollama_client import list_models

def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Configuration")

        st.subheader("Ollama")
        ollama_url = st.text_input(
            "Ollama base URL",
            value=st.session_state.get("ollama_url", "http://localhost:11434"),
            help="Default Ollama address. Change if running remotely.",
        )
        st.session_state["ollama_url"] = ollama_url

        available_models = []
        with st.spinner("Fetching models…"):
            try:
                available_models = list_models(ollama_url)
            except Exception:
                pass

        if available_models:
            default_idx = 0
            for i, m in enumerate(available_models):
                if any(k in m.lower() for k in ["llama3", "mistral", "qwen"]):
                    default_idx = i
                    break
            selected_model = st.selectbox(
                "Model",
                available_models,
                index=default_idx,
                help="Pick a model with good instruction-following (≥7B recommended).",
            )
        else:
            selected_model = st.text_input(
                "Model name",
                value=st.session_state.get("ollama_model", "llama3.1:8b"),
                help="Ollama not reachable — enter model name manually.",
            )
            if not available_models:
                st.warning(
                    "⚠️ Cannot reach Ollama. Make sure it is running:\n```\nollama serve\n```"
                )

        st.session_state["ollama_model"] = selected_model

        st.subheader("ChromaDB")
        chroma_path = st.text_input(
            "Persist directory",
            value=st.session_state.get("chroma_path", "./chroma_db"),
            help="Local path where ChromaDB stores ontology embeddings.",
        )
        st.session_state["chroma_path"] = chroma_path

        st.subheader("Pipeline options")
        st.session_state["temperature"] = st.slider(
            "LLM temperature", 0.0, 1.0,
            value=st.session_state.get("temperature", 0.1),
            step=0.05,
            help="Lower = more deterministic extraction.",
        )
        st.session_state["top_ontology_k"] = st.slider(
            "Ontology matches per entity", 1, 10,
            value=st.session_state.get("top_ontology_k", 3),
            help="How many ontology concepts to retrieve per entity.",
        )

        st.divider()
        st.subheader("Ontology seed")
        if st.button("🌱 Seed ontology into ChromaDB", use_container_width=True):
            with st.spinner("Seeding ontology…"):
                try:
                    from ontology.seeder import seed_ontology
                    n = seed_ontology(chroma_path)
                    st.success(f"✅ Seeded {n} ontology concepts.")
                except Exception as e:
                    st.error(f"Seed failed: {e}")

        st.divider()
        if st.button("🗑️ Clear results", use_container_width=True):
            st.session_state.pipeline_result = None
            st.rerun()
