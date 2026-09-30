import sys
from pathlib import Path

console_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(console_dir))

from app.main import app
from fastapi.testclient import TestClient


def test_routing_and_endpoints():
    client = TestClient(app)

    # 验证统一路由均正常返回 200，无 404
    assert client.get("/").status_code == 200
    assert client.get("/import").status_code == 200
    assert client.get("/tasks").status_code == 200
    assert client.get("/runs").status_code == 200
    assert client.get("/keyword").status_code == 200
    assert client.get("/keyword/tasks").status_code == 200
    assert client.get("/keyword/runs").status_code == 200
    assert client.get("/settings").status_code == 200

