"""The professor's skeleton (guidance.md A1–A6 + Đề tài 5 self_critique/gate), adapted only to run on our tools.

Same `build_graph(llm, retriever, db, web, callbacks)` signature as `src.graph` so eval can swap variants.
"""
from src.baseline.graph import build_graph

__all__ = ["build_graph"]
