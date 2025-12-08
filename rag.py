# rag.py
import os
import json
import chromadb

CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "./chroma_db")

client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
collection = client.get_or_create_collection(name="myfevent_kb")


def _raw_query(query, top_k, kb_groups=None):
    if not query or not str(query).strip():
        return []

    where = None
    if kb_groups:
        where = {"kb_group": {"$in": kb_groups}}

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where,
    )

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    ids_list = results.get("ids", [[]])[0]
    distances_list = results.get("distances", [[]])
    if distances_list:
        distances_list = distances_list[0]
    else:
        distances_list = [None] * len(docs)

    chunks = []
    for doc, meta, doc_id, distance in zip(docs, metas, ids_list, distances_list):
        raw_json = meta.get("raw_json")
        full_doc = None
        if raw_json:
            try:
                full_doc = json.loads(raw_json)
            except Exception:
                full_doc = None

        chunks.append(
            {
                "context": doc,
                "metadata": meta,
                "full_doc": full_doc,
                "doc_id": doc_id,
                "distance": distance,
            }
        )

    return chunks


def _filter_by_distance(chunks, max_distance=1.0):
    """
    Lọc các chunk có distance <= max_distance.
    Nếu distance là None -> tạm coi là không dùng (hoặc bạn có thể cho qua).
    """
    good = []
    for ch in chunks:
        dist = ch.get("distance")
        if dist is None:
            continue
        if dist <= max_distance:
            good.append(ch)
    return good


def retrieve_chunks(query, top_k=3, kb_groups=None, max_distance=None):
    """
    Nếu max_distance được set (vd 1.0), sẽ lọc theo ngưỡng.
    """
    chunks = _raw_query(query, top_k, kb_groups=kb_groups)
    if max_distance is not None:
        chunks = _filter_by_distance(chunks, max_distance=max_distance)
    return chunks


def retrieve_kb_for_event(
    query,
    top_k_user_events=4,
    top_k_patterns=2,
    max_distance=1.0,
):
    """
    - B1: thử lấy user_event, lọc theo max_distance
      + Nếu còn doc => trả user_event (+ pattern backup nếu muốn)
      + Nếu rỗng => thử pattern
    - B2: fallback sang pattern, cũng lọc theo max_distance
    - Nếu vẫn rỗng => trả []
    """

    # 1) Ưu tiên dữ liệu từ các sự kiện thực tế
    user_chunks_raw = _raw_query(
        query=query,
        top_k=top_k_user_events,
        kb_groups=["user_event"],
    )
    user_chunks = _filter_by_distance(user_chunks_raw, max_distance=max_distance)

    if user_chunks:
        pattern_chunks = []
        if top_k_patterns and top_k_patterns > 0:
            pattern_chunks_raw = _raw_query(
                query=query,
                top_k=top_k_patterns,
                kb_groups=["pattern"],
            )
            pattern_chunks = _filter_by_distance(
                pattern_chunks_raw, max_distance=max_distance
            )

        return user_chunks + pattern_chunks

    # 2) Nếu chưa có user_event phù hợp -> dùng pattern
    pattern_chunks_raw = _raw_query(
        query=query,
        top_k=top_k_user_events,
        kb_groups=["pattern"],
    )
    pattern_chunks = _filter_by_distance(pattern_chunks_raw, max_distance=max_distance)

    return pattern_chunks
