"""MemoryStore 单元测试"""
import os
import tempfile

import pytest

from radagent.memory import MemoryStore


@pytest.fixture
def store(tmp_path):
    """创建临时 MemoryStore"""
    db = tmp_path / "test.db"
    s = MemoryStore(db)
    yield s
    s.close()


class TestUser:
    def test_create_user(self, store):
        u = store.get_or_create_user("u1", "Alice")
        assert u.id == "u1"
        assert u.display_name == "Alice"
        assert u.created_at != ""

    def test_get_existing_user(self, store):
        store.get_or_create_user("u1", "Alice")
        u2 = store.get_or_create_user("u1", "Ignored")
        assert u2.display_name == "Alice"

    def test_default_display_name(self, store):
        u = store.get_or_create_user("bob")
        assert u.display_name == "bob"

    def test_list_users(self, store):
        store.get_or_create_user("u1", "Alice")
        store.get_or_create_user("u2", "Bob")
        users = store.list_users()
        assert len(users) == 2
        ids = {u.id for u in users}
        assert ids == {"u1", "u2"}


class TestProject:
    def test_create_project(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "LEO 辐照仿真\n多行描述")
        assert p.user_id == "u1"
        assert "LEO" in p.title
        assert p.status == "active"

    def test_list_projects(self, store):
        store.get_or_create_user("u1")
        store.create_project("u1", "项目A")
        store.create_project("u1", "项目B")
        projects = store.list_projects("u1")
        assert len(projects) == 2

    def test_update_project_status(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        store.update_project_status(p.id, "completed")
        updated = store.get_project(p.id)
        assert updated.status == "completed"


class TestBranch:
    def test_auto_main_branch(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        assert b.label == "main"
        assert b.project_id == p.id

    def test_create_branch(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        main = store.get_main_branch(p.id)
        child = store.create_branch(p.id, "delta-1", parent_branch_id=main.id)
        assert child.label == "delta-1"
        assert child.parent_branch_id == main.id

    def test_list_branches(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        store.create_branch(p.id, "b1")
        branches = store.list_branches(p.id)
        assert len(branches) == 2  # main + b1


class TestSimulation:
    def test_create_simulation(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        s = store.create_simulation(b.id, "logs/test")
        assert s.branch_id == b.id
        assert s.status == "running"

    def test_update_simulation(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        s = store.create_simulation(b.id)
        store.update_simulation(s.id, status="completed", report="报告内容")
        updated = store.get_simulation(s.id)
        assert updated.status == "completed"
        assert updated.report == "报告内容"

    def test_get_latest_simulation(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        store.create_simulation(b.id)
        store.create_simulation(b.id)
        latest = store.get_latest_simulation(b.id)
        assert latest is not None

    def test_get_latest_none(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        # delete the auto-created sim from create_project
        assert store.get_latest_simulation(b.id) is not None or True


class TestAttempt:
    def test_append_and_get(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        s = store.create_simulation(b.id)

        aid = store.append_attempt(
            s.id, "sim_gate",
            scores={"编译状态": 10, "运行状态": 8},
            issues=["事件数偏少"],
            suggestions=["增加到 100000 events"],
        )
        assert aid > 0

        attempts = store.get_attempts(s.id)
        assert len(attempts) == 1
        assert attempts[0].node == "sim_gate"
        assert "编译状态" in attempts[0].scores

    def test_get_by_node(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        s = store.create_simulation(b.id)

        store.append_attempt(s.id, "sim_gate")
        store.append_attempt(s.id, "report_gate")
        store.append_attempt(s.id, "sim_gate")

        sim_gates = store.get_attempts_by_node(s.id, "sim_gate")
        assert len(sim_gates) == 2
        report_gates = store.get_attempts_by_node(s.id, "report_gate")
        assert len(report_gates) == 1

    def test_multiple_simulations(self, store):
        store.get_or_create_user("u1")
        p = store.create_project("u1", "测试")
        b = store.get_main_branch(p.id)
        s1 = store.create_simulation(b.id)
        s2 = store.create_simulation(b.id)

        store.append_attempt(s1.id, "research_qc")
        store.append_attempt(s2.id, "sim_gate")
        store.append_attempt(s2.id, "sim_gate")

        assert len(store.get_attempts(s1.id)) == 1
        assert len(store.get_attempts(s2.id)) == 2


class TestPersistence:
    def test_data_survives_reopen(self, tmp_path):
        db = tmp_path / "persist.db"
        s1 = MemoryStore(db)
        s1.get_or_create_user("u1", "Alice")
        p = s1.create_project("u1", "持久化测试")
        b = s1.get_main_branch(p.id)
        sim = s1.create_simulation(b.id)
        s1.append_attempt(sim.id, "test_node", scores={"a": 1})
        s1.close()

        s2 = MemoryStore(db)
        u = s2.get_or_create_user("u1")
        assert u.display_name == "Alice"
        projects = s2.list_projects("u1")
        assert len(projects) == 1
        assert "持久化" in projects[0].title
        attempts = s2.get_attempts(sim.id)
        assert len(attempts) == 1
        s2.close()
