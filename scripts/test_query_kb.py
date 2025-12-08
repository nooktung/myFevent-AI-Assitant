# scripts/test_query_kb.py
import os
import sys
import json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from rag import retrieve_kb_for_event  # hoặc retrieve_chunks nếu cần thêm


def print_chunk_summary(idx, chunk):
    meta = chunk.get("metadata", {}) or {}
    doc = chunk.get("full_doc", {}) or {}

    kb_group = meta.get("kb_group")
    name = doc.get("name")
    event_type = doc.get("event_type")
    context = doc.get("context", "")

    epics = doc.get("epics", [])
    num_epics = len(epics)

    doc_id = chunk.get("doc_id")
    distance = chunk.get("distance")

    print(f"--- KB #{idx} ---")
    print(f"  doc_id    : {doc_id}")
    print(f"  distance  : {distance}")
    print(f"  kb_group  : {kb_group}")
    print(f"  name      : {name}")
    print(f"  event_type: {event_type}")
    print(f"  #epics    : {num_epics}")
    print("  context   :")
    print("   ", (context[:180] + "...") if len(context) > 180 else context)

    if epics:
        first_epic = epics[0]
        print("  first_epic:")
        print("    department :", first_epic.get("department"))
        print("    title      :", first_epic.get("title"))
        tasks = first_epic.get("tasks", [])
        print("    #tasks     :", len(tasks))
    print()


def test_queries():
    queries = [
        "workshop AI cho sinh viên, có livestream, quy mô 150-200 người",
        "orientation game day cho tân sinh viên, nhiều game station",
        "ngày hội việc làm career fair cho sinh viên, nhiều booth doanh nghiệp",
        "đêm nhạc Music Night của CLB âm nhạc cho sinh viên",
    ]

    for q in queries:
        print("=" * 80)
        print("QUERY:", q)
        print("=" * 80)

        chunks = retrieve_kb_for_event(
            query=q,
            top_k_user_events=4,
            top_k_patterns=2,
        )

        if not chunks:
            print(">> Không tìm thấy KB nào.")
            continue

        for idx, ch in enumerate(chunks, start=1):
            print_chunk_summary(idx, ch)

        print("\n\n")


if __name__ == "__main__":
    test_queries()
