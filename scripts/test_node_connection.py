# scripts/test_node_connection.py
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from tools.node_client import get


def main():
    base_url = os.getenv("MYFEVENT_BASE_URL", "http://localhost:8080/api/events")
    print(f"Testing connection to backend: {base_url}")

    try:
        # Sẽ gọi: GET {base_url}/public?page=1&limit=5
        res = get("/public", params={"page": 1, "limit": 5}, user_token=None)
        print("✅ Kết nối thành công, backend trả về:")
        print(res)
    except Exception as e:
        print("❌ Lỗi khi gọi backend:")
        print(repr(e))


if __name__ == "__main__":
    main()
