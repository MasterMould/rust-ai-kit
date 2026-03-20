# ui/tab_benchmark.py — GPU Benchmark tab (mirrors option 12 in ai_stack_manager.sh)
import streamlit as st

from core.config import BackendMode, ENGINE_PORT, STACK_LOG_DIR
from core.auth   import audit_log
from core.stack  import StackManager

def tab_benchmark():
    st.header("📊 GPU Benchmark")

    if st.session_state.backend != BackendMode.RUSTAIKIT.value:
        st.info("Benchmark targets the rust-ai-kit llama-server.")
        return

    st.info(
        "Replicates **option 12** from `ai_stack_manager.sh`:  \n"
        f"POSTs a 200-token completion to `:{ENGINE_PORT}/v1/completions` "
        "and calculates tokens/second.  \n"
        "**Expected on Intel Arc A770 (SYCL):** ~25–45 tok/s for 8B Q4_K_M"
    )

    if not StackManager.engine_running():
        st.error("Engine offline — start it from the Stack tab first.")
        return

    if st.button("🚀 Run Benchmark", type="primary"):
        with st.spinner("Running 200-token completion…"):
            result = StackManager.benchmark()

        if not result.get("ok"):
            st.error(f"Benchmark failed: {result.get('error', 'unknown error')}")
            st.caption(f"Check: `tail -f {STACK_LOG_DIR}/engine.log`")
            return

        tps = result["tps"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Tokens generated", result["tokens"])
        c2.metric("Elapsed",          f"{result['elapsed_ms']:,} ms")
        c3.metric("Throughput",        f"{tps} tok/s")

        if isinstance(tps, (int, float)) and tps > 0:
            if tps < 10:
                st.error(
                    "⚠️ Below 10 tok/s — SYCL GPU acceleration likely NOT active.  \n"
                    "Check the Stack tab: GPU must be visible and engine started with "
                    f"`--n-gpu-layers 99`.  \n"
                    f"Verify: `clinfo -l | grep -i intel`"
                )
            elif tps < 25:
                st.warning("Throughput below expected range — partial CPU offload likely.")
            else:
                st.success(f"✅ {tps} tok/s — GPU acceleration confirmed")

        if result.get("text"):
            with st.expander("Generated text"):
                st.write(result["text"])

        audit_log(st.session_state.username, "BENCHMARK",
                  f"tps={tps} tokens={result['tokens']}", True)


# ============================================================================
# TAB: SECURITY
# ============================================================================
