import io
import stat
import zipfile

import httpx
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from packages.contracts.auth import UserPublic
from services.api_manager.api.routes import models, simulations
from services.api_manager.auth.dependencies import get_current_user
from services.api_manager.execution.remote_executor import RemoteSimulationExecutor
from services.api_manager.main import app
from services.api_manager.orchestration.custom_models import custom_model_manager
from services.api_manager.orchestration.custom_models import CustomModelManager
from services.api_manager.orchestration.simulation_service import SimulationService
from services.api_manager.platform.settings import settings
from services.simulation_worker import main as worker
from services.simulation_worker.executor import LocalSimulationExecutor


MASTER = """Clear
New Circuit.fixture bus1=source basekv=12.47 pu=1 phases=3
Redirect components/Feeder.dss
New LoadShape.test npts=3 interval=1 mult=(file=../profiles/Daily.CSV, col=1, header=no)
New Load.demand bus1=load.1.2.3 phases=3 conn=wye kV=12.47 kW=100 pf=0.95 daily=test
Set VoltageBases="12.47, .48"
CalcVoltageBases
"""
FEEDER = "New Line.feeder bus1=source.1.2.3 bus2=load.1.2.3 phases=3 r1=0.1 x1=0.1 length=1\n"
MASTER_PATH = "feeder/MASTER.DSS"
ADMIN = {"X-Test-User": "admin"}


def archive(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as model_zip:
        for member, content in entries:
            model_zip.writestr(member, content)
    return data.getvalue()


@pytest.fixture(params=["local", "remote"])
def laboratory(monkeypatch, tmp_path, request):
    root = tmp_path / "custom-models"
    monkeypatch.setattr(custom_model_manager, "root", root)
    monkeypatch.setenv("CUSTOM_MODELS_DIR", str(root))
    monkeypatch.setattr(settings, "allow_custom_models", True)
    monkeypatch.setattr(settings, "rate_limit_enabled", False)
    monkeypatch.delenv("WORKER_SHARED_TOKEN_FILE", raising=False)
    monkeypatch.setenv("WORKER_SHARED_TOKEN", "worker-fixture-key")

    def user(request: Request):
        username = request.headers.get("X-Test-User", "reader")
        return UserPublic(username=username, role="admin" if username == "admin" else "user")

    monkeypatch.setitem(app.dependency_overrides, get_current_user, user)
    executor = LocalSimulationExecutor()
    if request.param == "remote":
        monkeypatch.setattr(worker, "executor", executor)
        remote = RemoteSimulationExecutor(base_url="http://worker")
        monkeypatch.setattr(remote, "_client", lambda: httpx.AsyncClient(
            transport=httpx.ASGITransport(app=worker.app, raise_app_exceptions=False),
            base_url="http://worker",
            headers={"Authorization": "Bearer worker-fixture-key"},
        ))
        executor = remote

    monkeypatch.setattr(models, "simulation_executor", executor)
    monkeypatch.setattr(simulations, "simulation_service", SimulationService(executor))
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, root


def upload_zip(client):
    payload = archive([
        (MASTER_PATH, MASTER),
        ("feeder/components/Feeder.dss", FEEDER),
        ("profiles/Daily.CSV", "1\n0.65\n1.15\n"),
    ])
    response = client.post("/models/upload", files={"file": ("prueba.zip", payload)}, headers=ADMIN)
    assert response.status_code == 201, response.text
    return response.json()


def test_custom_catalog_and_model_execute_snapshot_and_qsts(laboratory):
    client, root = laboratory
    metadata = upload_zip(client)
    assert metadata["recommended_master"] == MASTER_PATH
    assert metadata["masters"] == ["feeder/components/Feeder.dss", MASTER_PATH]
    assert "workspace" not in metadata
    model_id = metadata["model_id"]
    catalog = client.get("/models/custom", headers=ADMIN)
    assert catalog.status_code == 200
    assert [item["model_id"] for item in catalog.json()] == [model_id]
    reloaded_catalog = CustomModelManager()
    reloaded_catalog.root = root
    assert reloaded_catalog.list_models() == catalog.json()
    assert client.get("/models/custom").status_code == 403
    assert client.get(f"/models/custom/{model_id}").status_code == 403
    topology = {"topology": f"custom:{model_id}:{MASTER_PATH}"}
    assert client.post("/simulations", json=topology).status_code == 403
    validated = client.post(f"/models/custom/{model_id}/validate", params={"master": MASTER_PATH}, headers=ADMIN)
    assert validated.status_code == 200 and validated.json()["valid"] is True, validated.text

    created = client.post("/simulations", json=topology, headers=ADMIN)
    assert created.status_code == 201, created.text
    path = f"/simulations/{created.json()['session_id']}"
    try:
        session_id = created.json()["session_id"]
        public_summary = next(item for item in client.get("/simulations").json() if item["session_id"] == session_id)
        assert public_summary["topology"] == "custom"
        snapshot = client.post(f"{path}/solve", headers=ADMIN)
        assert snapshot.status_code == 200 and snapshot.json()["converged"] is True
        qsts = client.post(f"{path}/solve", json={"simulation_type": "qsts", "qsts": {
            "duration_hours": 3, "step_minutes": 60, "profile_source": "model",
        }}, headers=ADMIN)
        assert qsts.status_code == 200 and qsts.json()["summary"]["converged_steps"] == 3
        steps = client.get(f"{path}/results", headers=ADMIN).json()["steps"]
        assert len({round(abs(step["total_kw"]), 1) for step in steps}) == 3
        assert (root / model_id / MASTER_PATH).is_file()
    finally:
        assert client.delete(path, headers=ADMIN).status_code == 204


def test_invalid_edit_leaves_published_master_intact(laboratory):
    client, _ = laboratory
    model_id = upload_zip(client)["model_id"]
    path = f"/models/custom/{model_id}/files/{MASTER_PATH}"
    rejected = client.put(path, json={"content": "New Line.incomplete phases=3"}, headers=ADMIN)
    assert rejected.status_code == 400
    assert client.get(path, headers=ADMIN).json()["content"] == MASTER

    edited = MASTER.replace("kW=100", "kW=115")
    saved = client.put(path, json={"content": edited}, headers=ADMIN)
    assert saved.status_code == 200, saved.text
    assert client.get(path, headers=ADMIN).json()["content"] == edited


def test_archive_limits_and_case_collisions_are_rejected(laboratory, monkeypatch):
    client, root = laboratory
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    for entries in (
        [("Master.dss", MASTER), ("MASTER.DSS", MASTER)],
        [("Master.dss", MASTER), ("profiles/data.csv", "0\n" * 600_000)],
        [("Master.dss", MASTER), ("nested/../data.csv", "1\n")],
    ):
        response = client.post("/models/upload", files={"file": ("invalid.zip", archive(entries))}, headers=ADMIN)
        assert response.status_code == 400
    assert not any(folder.name[0].isalnum() for folder in root.iterdir())

    link = zipfile.ZipInfo("linked.dss")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    response = client.post("/models/upload", files={"file": ("link.zip", archive([(link, "Master.dss")]))}, headers=ADMIN)
    assert response.status_code == 400


def test_ambiguous_masters_require_selection_and_paths_keep_exact_case(laboratory):
    client, _ = laboratory
    payload = archive([
        ("first/Master.dss", "New Circuit.first bus1=a basekv=12.47\n"),
        ("second/Main.dss", "New Circuit.second bus1=b basekv=12.47\n"),
    ])
    uploaded = client.post("/models/upload", files={"file": ("ambiguous.zip", payload)}, headers=ADMIN)
    assert uploaded.status_code == 201
    model = uploaded.json()
    assert model["recommended_master"] is None
    base = f"/models/custom/{model['model_id']}"
    wrong_case = client.post(base + "/validate", params={"master": "first/master.dss"}, headers=ADMIN)
    assert wrong_case.status_code == 400
    assert "mayúsculas" in wrong_case.json()["detail"]
    valid = client.post(base + "/validate", params={"master": "second/Main.dss"}, headers=ADMIN)
    assert valid.json()["valid"] is True


def test_custom_validation_rejects_unavailable_dependency_and_unsupported_command(laboratory):
    client, root = laboratory
    base = "New Circuit.fixture bus1=source basekv=12.47\n"
    for invalid, message in (
        (base + "Redirect absent.dss\n", "absent.dss"),
        (base + "Set DataPath=other\n", "datapath"),
    ):
        payload = archive([("Master.dss", invalid)])
        uploaded = client.post("/models/upload", files={"file": ("invalid.zip", payload)}, headers=ADMIN)
        assert uploaded.status_code == 201
        model_id = uploaded.json()["model_id"]
        validated = client.post(f"/models/custom/{model_id}/validate", params={"master": "Master.dss"}, headers=ADMIN)
        assert validated.status_code == 200
        assert validated.json()["valid"] is False
        assert message in validated.json()["message"]
        assert str(root) not in validated.json()["message"]
        created = client.post("/simulations", json={"topology": f"custom:{model_id}:Master.dss"}, headers=ADMIN)
        assert created.status_code == 400


def test_disabling_custom_models_blocks_creation_and_hides_catalog(laboratory, monkeypatch):
    client, _ = laboratory
    model_id = upload_zip(client)["model_id"]
    monkeypatch.setattr(settings, "allow_custom_models", False)
    assert client.get("/models/custom", headers=ADMIN).json() == []
    created = client.post("/simulations", json={"topology": f"custom:{model_id}:{MASTER_PATH}"}, headers=ADMIN)
    assert created.status_code == 400
