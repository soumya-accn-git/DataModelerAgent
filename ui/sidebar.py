import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import streamlit as st
from agent.ollama_client import list_models

# Load all credentials from Neo4j_instance_detl.txt via config.py
from config import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE,
    AURA_INSTANCEID, AURA_INSTANCENAME, OLLAMA_URL, CHROMA_PATH,
)

def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Configuration")

        st.subheader("Ollama")
        ollama_url = st.text_input(
            "Base URL",
            value=st.session_state.get("ollama_url", OLLAMA_URL),
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
            value=st.session_state.get("chroma_path", CHROMA_PATH),
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
        st.subheader("Neo4j GraphRAG")
        st.caption(
            f"Instance: **{AURA_INSTANCENAME}** · ID: `{AURA_INSTANCEID}`  \n"
            f"Credentials loaded from `Neo4j_instance_detl.txt`"
        )
        st.session_state["neo4j_uri"] = st.text_input(
            "Neo4j URI",
            value=st.session_state.get("neo4j_uri", NEO4J_URI),
            help="bolt://localhost:7687 for local · neo4j+s://... for Aura cloud",
        )
        st.session_state["neo4j_user"] = st.text_input(
            "Username",
            value=st.session_state.get("neo4j_user", NEO4J_USER),
        )
        st.session_state["neo4j_password"] = st.text_input(
            "Password",
            value=st.session_state.get("neo4j_password", NEO4J_PASSWORD),
            type="password",
        )
        neo4j_ok   = False
        neo4j_err  = ""
        try:
            from neo4j import GraphDatabase, version as neo4j_ver
        except ImportError:
            neo4j_err = "neo4j package not installed — run: pip install 'neo4j>=5.0.0'"

        if not neo4j_err:
            try:
                uri  = st.session_state["neo4j_uri"]
                user = st.session_state["neo4j_user"]
                pwd  = st.session_state["neo4j_password"]

                # neo4j+s:// handles SSL automatically in driver v5+
                # Do NOT pass encrypted= kwarg — it is deprecated in v5
                d = GraphDatabase.driver(
                    uri,
                    auth=(user, pwd),
                    connection_timeout=10,    # fail fast in sidebar check
                    max_connection_lifetime=30,
                )
                d.verify_connectivity()
                d.close()
                neo4j_ok = True
            except Exception as ex:
                neo4j_err = str(ex)[:200]

        if neo4j_ok:
            st.success("✅ Neo4j Aura connected")
        else:
            st.warning("⚠️ Neo4j not reachable — fallback mode active")
            if neo4j_err:
                with st.expander("🔍 Connection error details"):
                    st.code(neo4j_err)
                    st.caption(
                        "Common fixes:\n"
                        "1. Run: `pip install 'neo4j>=5.0.0'`\n"
                        "2. Check URI starts with `neo4j+s://` for Aura\n"
                        "3. Verify username matches Aura connection file (NEO4J_USERNAME)\n"
                        "4. Check your firewall allows outbound port 7687"
                    )

        # ── Manual test button ────────────────────────────────────────────
        if st.button("🔌 Test Neo4j connection", use_container_width=True):
            with st.spinner("Connecting to Neo4j…"):
                # Show which Python is running to help debug venv issues
                import sys
                st.caption(f"Python: `{sys.executable}`")
                try:
                    from neo4j import GraphDatabase
                    _uri  = st.session_state.get("neo4j_uri", NEO4J_URI)
                    _user = st.session_state.get("neo4j_user", NEO4J_USER)
                    _pwd  = st.session_state.get("neo4j_password", NEO4J_PASSWORD)

                    d = GraphDatabase.driver(
                        _uri,
                        auth=(_user, _pwd),
                        connection_timeout=15,
                    )
                    d.verify_connectivity()

                    # Run a quick Cypher query to confirm read access
                    with d.session() as session:
                        info = session.run(
                            "CALL dbms.components() YIELD name, versions RETURN name, versions LIMIT 1"
                        ).single()
                        db_name    = info["name"] if info else "Neo4j"
                        db_version = info["versions"][0] if info and info["versions"] else "?"

                    # Count existing nodes and relationships
                    with d.session() as session:
                        counts = session.run(
                            "MATCH (n) RETURN count(n) AS nodes "
                            "UNION ALL "
                            "MATCH ()-[r]->() RETURN count(r) AS nodes"
                        ).data()
                        node_count = counts[0]["nodes"] if counts else 0
                        rel_count  = counts[1]["nodes"] if len(counts) > 1 else 0

                    d.close()

                    st.success(
                        f"✅ Connected to **{db_name}** v{db_version}  \n"
                        f"📊 **{node_count:,}** nodes · **{rel_count:,}** relationships in database"
                    )

                except ImportError:
                    st.error("❌ neo4j package not installed.  \nRun: `pip install 'neo4j>=5.0.0'`")
                except Exception as ex:
                    st.error(f"❌ Connection failed")
                    st.code(str(ex))
                    st.caption(
                        "Tips:\n"
                        "• Username for Aura Free is always `neo4j`\n"
                        "• URI should start with `neo4j+s://`\n"
                        "• Check password in Neo4j Aura console → Connect tab"
                    )

        st.subheader("Document parser")
        parser_choice = st.radio(
            "Parser priority",
            ["Auto (LlamaParse → Unstructured → python-docx)", "python-docx only"],
            index=0,
            label_visibility="collapsed",
            help="Auto tries best available. Set LLAMA_CLOUD_API_KEY env var for LlamaParse.",
        )
        st.session_state["parser_mode"] = parser_choice

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

        if st.button("🔬 Seed Oracle RDM (all 927 entities)", use_container_width=True):
            with st.spinner("Seeding all Oracle RDM entities + tables…"):
                try:
                    from agent.oracle_rdm_seeder import seed_oracle_rdm
                    ph = st.empty()
                    counts = seed_oracle_rdm(
                        chroma_path=st.session_state.get("chroma_path", "./chroma_db"),
                        on_log=lambda m: ph.caption(m),
                    )
                    ph.empty()
                    ldm_n = counts.get("ldm", 0)
                    pdm_n = counts.get("pdm", 0)
                    if ldm_n == 0 and pdm_n == 0:
                        st.info("Already seeded — brd_domain=Y filter applied at query time")
                    else:
                        st.success(
                            "✅ Seeded: oracle_rdm_ldm=" + str(ldm_n) +
                            " entities, oracle_rdm_pdm=" + str(pdm_n) + " tables"
                        )
                except FileNotFoundError as fe:
                    st.error("JSON files not found. Run PDF extractor first. " + str(fe))
                except Exception as e:
                    st.error("Oracle RDM seed failed: " + str(e))

        # Pipeline mode is chosen from run buttons in the upload panel
        mode = st.session_state.get("pipeline_mode", "CDM only")
        mode_colors = {
            "CDM only":  "#E1F5EE",
            "CDM + LDM": "#E6F1FB",
            "LDM only":  "#FAEEDA",
        }
        bg = mode_colors.get(mode, "#F3F4F6")
        st.markdown(
            f'<div style="background:{bg};border-radius:6px;padding:.4rem .7rem;'
            f'font-size:12px;font-weight:500;margin-top:.5rem">'
            f'Mode: {mode}</div>',
            unsafe_allow_html=True,
        )

        st.divider()
        st.subheader("Stored results")
        try:
            from agent.result_store import list_stored
            import time as _time
            stored = list_stored()
            if stored:
                for r in stored[:5]:
                    cdm_badge = "CDM ✅" if r["has_cdm"] else "CDM —"
                    ldm_badge = "LDM ✅" if r["has_ldm"] else "LDM —"
                    ts = _time.strftime("%d %b %H:%M", _time.localtime(r["modified"]))
                    st.caption(f"`{r['brd_hash']}` · {cdm_badge} · {ldm_badge} · {ts}")
            else:
                st.caption("No results stored yet.")
        except Exception:
            st.caption("Run a pipeline to store results.")

        if st.button("🗑️ Clear results", use_container_width=True):
            st.session_state.pipeline_result = None
            st.session_state.pop("ldm_result", None)
            st.rerun()