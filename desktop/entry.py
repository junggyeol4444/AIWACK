"""Entry point for python -m desktop.entry and bundled Windows AIWACK.exe."""
import sys


def self_test() -> int:
    """Real offline authentication, note persistence, and reopen using a disposable DB."""
    from pathlib import Path
    import tempfile
    from desktop.storage import AuthenticationError, LocalStore

    with tempfile.TemporaryDirectory(prefix="aiwack-exe-check-") as directory:
        path = Path(directory) / "test.sqlite3"
        instance = LocalStore(path)
        try:
            instance.read_note()
            return 1  # Fail closed without a session.
        except AuthenticationError:
            pass
        instance.setup_owner("exe_tester", "test-password-long-2026")
        instance.save_note("desktop-startup-ok")
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.read_note()
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_note() != "desktop-startup-ok":
            return 1
        if instance.health()["status"] != "ok":
            return 1
        # Exercise Stage 11 using the *compiled Windows EXE process*, not just pytest.
        instance.save_company("EXE company", "Real Windows binary", "Verify durable goals")
        goal_id = instance.add_goal("ship runnable exe", "stage 11 runtime")
        instance.update_goal(goal_id, "ship verified exe", "stage 11 runtime", "active")
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_company()["name"] != "EXE company":
            return 1
        if instance.list_goals() != [{"id": goal_id, "title": "ship verified exe", "detail": "stage 11 runtime", "status": "active"}]:
            return 1
        instance.delete_goal(goal_id)
        if instance.list_goals():
            return 1
        # Stage 12: exercise persistent department CRUD *inside* built EXE.
        department_id = instance.add_department("EXE Research", "real binary database test")
        instance.update_department(department_id, "EXE Research Lab", "persist after restart")
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if instance.list_departments() != [{"id": department_id,
                                           "name": "EXE Research Lab",
                                           "description": "persist after restart"}]:
            return 1
        instance.delete_department(department_id)
        if instance.list_departments():
            return 1
        # Stage 13: compiled Windows binary exercises catalog CRUD, persistence,
        # role classification and session restrictions (not permission grants).
        rank_id = instance.add_designation("rank", "EXE 팀장", "level test")
        job_id = instance.add_designation("job", "EXE 개발", "work test")
        role_id = instance.add_designation("role", "EXE 검수", "responsibility test")
        instance.update_designation(role_id, "role", "EXE 품질검수", "quality test")
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.list_designations()
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if [(item["kind"], item["name"]) for item in instance.list_designations()] != [
            ("rank", "EXE 팀장"), ("job", "EXE 개발"), ("role", "EXE 품질검수")
        ]:
            return 1
        for identifier in (rank_id, job_id, role_id):
            instance.delete_designation(identifier)
        if instance.list_designations():
            return 1
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    from desktop.app import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
