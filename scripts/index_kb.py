# scripts/index_kb.py
import json
import uuid
import chromadb
import os
from chromadb.utils import embedding_functions

CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", "./chroma_db")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Tạo embedding function sử dụng OpenAI
def create_embedding_function():
    """
    Tạo embedding function cho ChromaDB.
    Nếu có OPENAI_API_KEY -> dùng OpenAI embeddings
    Ngược lại -> dùng default embedding của ChromaDB
    """
    if OPENAI_API_KEY:
        # Sử dụng OpenAI embedding function
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=OPENAI_API_KEY,
            model_name="text-embedding-3-small"  # Model nhẹ và hiệu quả
        )
    else:
        # Fallback về default embedding của ChromaDB
        print("[WARN] OPENAI_API_KEY không được set, sử dụng default embedding của ChromaDB")
        return embedding_functions.DefaultEmbeddingFunction()

# Khởi tạo ChromaDB client với embedding function
embedding_fn = create_embedding_function()
client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
collection = client.get_or_create_collection(
    name="myfevent_kb",
    embedding_function=embedding_fn
)

# Các thư mục KB sẽ scan
KB_DIRS = [
    os.path.join("kb", "patterns"),
    os.path.join("kb", "user_events"),
]


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_json_files():
    """Duyệt tất cả file .json trong các thư mục KB_DIRS."""
    for base in KB_DIRS:
        if not os.path.exists(base):
            continue
        for root, _, files in os.walk(base):
            for fname in files:
                if fname.lower().endswith(".json"):
                    yield os.path.join(root, fname)


def detect_kb_group(path: str) -> str:
    """
    Phân loại KB theo đường dẫn file:
    - chứa 'user_events' -> 'user_event'
    - ngược lại -> 'pattern'
    """
    norm = path.replace("\\", "/")
    if "user_events" in norm:
        return "user_event"
    return "pattern"


def index_file(path: str):
    data = load_json(path)

    # Cho phép file chứa 1 object hoặc 1 list object
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        print(f"[WARN] File {path} không phải dict/list hợp lệ, bỏ qua.")
        return

    docs = []
    metadatas = []
    ids = []

    kb_group = detect_kb_group(path)

    for item in items:
        # Lấy trường "context" từ item để embed
        context = item.get("context")
        if not context or not str(context).strip():
            # Bắt buộc phải có context để embed, bỏ qua nếu không có
            continue

        _id = item.get("id") or str(uuid.uuid4())
        raw_json = json.dumps(item, ensure_ascii=False)

        meta = {
            "id": _id,
            "source_file": path,
            "kb_group": kb_group,   # 'pattern' hoặc 'user_event'
            "raw_json": raw_json,   # full tài liệu để LLM dùng
        }
        if item.get("type") is not None:
            meta["type"] = str(item["type"])
        if item.get("event_type") is not None:
            meta["event_type"] = str(item["event_type"])
        if item.get("name") is not None:
            meta["name"] = str(item["name"])

        # Thêm trường "context" vào docs để ChromaDB embed thành vector
        docs.append(str(context))
        metadatas.append(meta)
        ids.append(_id)

    if docs:
        # Thêm documents vào ChromaDB với embedding tự động
        # ChromaDB sẽ tự động gọi embedding function để tạo vector cho mỗi document
        collection.add(
            documents=docs,
            metadatas=metadatas,
            ids=ids,
        )
        print(f"[OK] Indexed {len(docs)} docs from {path} (embeddings created)")
    else:
        print(f"[SKIP] No valid docs in {path}")


def main():
    # Hiển thị thông tin về embedding function đang sử dụng
    if OPENAI_API_KEY:
        print(f"[INFO] Sử dụng OpenAI embeddings (model: text-embedding-3-small)")
    else:
        print(f"[INFO] Sử dụng default embedding của ChromaDB")
    
    any_file = False
    for path in iter_json_files():
        any_file = True
        try:
            index_file(path)
        except Exception as e:
            print(f"[ERROR] Index {path} failed: {e}")

    if not any_file:
        print("[WARN] Không tìm thấy file KB nào trong kb/patterns hoặc kb/user_events.")
    else:
        print(f"[INFO] Hoàn thành indexing. Tổng số documents trong collection: {collection.count()}")


if __name__ == "__main__":
    main()
