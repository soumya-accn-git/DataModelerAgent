import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
from agent.ollama_client import list_models

def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Configuration")

        st.subheader("Ollama")
        ollama_url = st.text_input(
            "Base URL",
            value=st.session_state.get("ollama_url", "http://localhost:11434"),
        )
        st.session_state["ollama_url"] = ollama_url

        available_models = []
        try:
            available_models = list_models(ollama_url)
        except Exception:
            pass

        if available_models:
            default_idx = 0
            for i, m in enumerate(available_models):
                if any(k in m.lower() for k in ["llama3","mistral","qwen"]):
                    default_idx = i; break
            selected_model = st.selectbox("Model", available_models, index=default_idx)
        else:
            selected_model = st.text_input(
                "Model name",
                value=st.session_state.get("ollama_model","llama3.1:8b"),
            )
            st.warning("⚠️ Ollama not reachable. Run: `ollama serve`")

        st.session_state["ollama_model"] = selected_model

        st.subheader("ChromaDB")
        st.session_state["chroma_path"] = st.text_input(
            "Persist directory",
            value=st.session_state.get("chroma_path","./chroma_db"),
        )

        st.subheader("Pipeline options")
        st.session_state["temperature"] = st.slider(
            "LLM temperature", 0.0, 1.0,
            value=st.session_state.get("temperature", 0.1), step=0.05,
        )
        st.session_state["top_ontology_k"] = st.slider(
            "Ontology matches / entity", 1, 10,
            value=st.session_state.get("top_ontology_k", 3),
        )

        st.divider()
        st.subheader("Ontology")
        if st.button("🌱 Seed ontology into ChromaDB", use_container_width=True):
            with st.spinner("Seeding…"):
                try:
                    from ontology.seeder import seed_ontology
                    n = seed_ontology(st.session_state["chroma_path"])
                    st.success(f"✅ Seeded {n} concepts.")
                except Exception as e:
                    st.error(f"Seed failed: {e}")

        st.divider()
        if st.button("🗑️ Clear results", use_container_width=True):
            st.session_state.pipeline_result = None
            st.rerun()