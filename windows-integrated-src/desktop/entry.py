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
        # Stage 22: create, edit, re-open, and remove manually authored plans.
        plan_id = instance.add_work_plan(goal_id, "Local stage22 plan", "No task execution",
                                         ["Draft steps", "Review plan"])
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.list_work_plans()
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_work_plan(plan_id)["steps"] != ["Draft steps", "Review plan"]:
            return 1
        instance.update_work_plan(plan_id, goal_id, "Verified offline plan", "Local-only",
                                  ["Prepare", "Review", "Save"], "ready")
        try:
            instance.delete_goal(goal_id)
            return 1
        except ValueError:
            pass
        if instance.read_work_plan(plan_id)["status"] != "ready":
            return 1
        # Stage 23: compiled EXE tests task lifecycle, status audit,
        # plan FK protection and persistence across a fresh authenticated store.
        task_id = instance.add_task("EXE offline task", "owner manually authored", plan_id)
        instance.set_task_status(task_id, "in_progress")
        instance.set_task_status(task_id, "done")
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.read_task(task_id)
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_task(task_id)["status"] != "done":
            return 1
        if len(instance.list_task_status_events(task_id)) != 3:
            return 1
        try:
            instance.delete_work_plan(plan_id)
            return 1
        except ValueError:
            pass
        instance.set_task_status(task_id, "todo")
        # Stage26: prerequisite guard, restart and audit in the same offline EXE check.
        upstream_id = instance.add_task("EXE stage26 prerequisite")
        if not instance.add_task_dependency(task_id, upstream_id):
            return 1
        try:
            instance.set_task_status(task_id, "in_progress")
            return 1
        except ValueError:
            pass
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if instance.task_dependency_readiness(task_id)["pending_ids"] != [upstream_id]:
            return 1
        instance.set_task_status(upstream_id, "in_progress")
        instance.set_task_status(upstream_id, "done")
        if not instance.task_dependency_readiness(task_id)["ready"]:
            return 1
        if not instance.remove_task_dependency(task_id, upstream_id):
            return 1
        if [x["action"] for x in instance.list_task_dependency_events(task_id)] != ["added", "removed"]:
            return 1
        instance.set_task_status(upstream_id, "todo")
        instance.delete_task(upstream_id)
        instance.update_task(task_id, "EXE reopened task", "no network", None)
        if instance.list_tasks(plan_id) or instance.read_task(task_id)["plan_id"] is not None:
            return 1
        instance.delete_task(task_id)
        if instance.list_tasks():
            return 1
        instance.delete_work_plan(plan_id)
        instance.delete_goal(goal_id)
        if instance.list_goals() or instance.list_work_plans():
            return 1
        # Stage 27: verify the new offline execution schema and fail-closed
        # preflight without starting any executable (EXE self-test is safe).
        stage27_task = instance.add_task('EXE stage27 preflight')
        try:
            instance.begin_task_execution(stage27_task)
            return 1  # No assigned local AI model: execution must be denied.
        except ValueError:
            pass
        if instance.list_task_runs(stage27_task):
            return 1
        instance.delete_task(stage27_task)
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
        # Stage 14: the COMPILED Windows EXE must verify actual FK-backed draft
        # persistence across a fresh LocalStore and closed SQLite handles.
        department_id = instance.add_department("EXE Agent Team", "metadata only")
        employee_id = instance.add_employee_draft(
            "exe_employee_001", "EXE 직원 정보", "실행하지 않는 초안",
            department_id=department_id, rank_id=rank_id, job_id=job_id, role_id=role_id,
        )
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.list_employee_records()
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        profile = instance.read_employee_record(employee_id)
        if profile["lifecycle"] != "draft" or profile["department_id"] != department_id:
            return 1
        if (profile["rank_id"], profile["job_id"], profile["role_id"]) != (rank_id, job_id, role_id):
            return 1
        try:
            instance.delete_department(department_id)
            return 1  # referenced department must not be silently destroyed.
        except ValueError:
            pass
        # Stage 15: the real compiled binary exercises updates, inactivation,
        # persistence and reactivation; no AI model should be started.
        instance.update_employee_record(employee_id, "EXE 수정된 직원", "수정 후에도 안전한 초안",
                                        department_id=department_id, rank_id=rank_id,
                                        job_id=job_id, role_id=role_id)
        instance.set_employee_inactive(employee_id)
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if (instance.read_employee_record(employee_id)["lifecycle"] != "inactive" or
                instance.read_employee_record(employee_id)["display_name"] != "EXE 수정된 직원"):
            return 1
        instance.restore_employee_draft(employee_id)
        if instance.read_employee_record(employee_id)["lifecycle"] != "draft":
            return 1
        # Stage 16: verify reporting lines, persistence, and authority constraints.
        instance.update_employee_record(employee_id, "EXE 수정된 직원", "CEO 초안", department_id=None)
        instance.assign_reporting_line(employee_id, "ceo")
        subordinate_department = instance.add_department("EXE Hierarchy", "stage16 local")
        head = instance.add_employee_draft("exe_head_001", "EXE 부서장", department_id=subordinate_department)
        subordinate = instance.add_employee_draft("exe_staff_001", "EXE 직원", department_id=subordinate_department)
        instance.assign_reporting_line(head, "department_head", employee_id)
        instance.assign_reporting_line(subordinate, "staff", head)
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if len(instance.list_reporting_lines()) != 3:
            return 1
        try:
            instance.unassign_reporting_line(employee_id)
            return 1
        except ValueError:
            pass
        instance.unassign_reporting_line(subordinate)
        instance.unassign_reporting_line(head)
        instance.unassign_reporting_line(employee_id)
        with instance._connect() as con:
            con.execute("DELETE FROM ai_employee_profiles WHERE id IN (?, ?)", (head, subordinate))
        instance.delete_department(subordinate_department)
        # Restore original metadata for final stage-15 cleanup.
        instance.update_employee_record(employee_id, "EXE 수정된 직원", "수정 후에도 안전한 초안",
                                        department_id=department_id, rank_id=rank_id,
                                        job_id=job_id, role_id=role_id)
        # Stage 17: the *packaged EXE* checks deny-by-default, durable grants,
        # no owner-right delegation, lifecycle revocation and fresh login.
        if instance.is_employee_allowed(employee_id, "company:read"):
            return 1
        instance.save_employee_access(employee_id, ["company:read", "goals:read"],
                                      ["local_company_reader"])
        instance.require_employee_access(employee_id, "company:read", "local_company_reader")
        if instance.is_employee_allowed(employee_id, "tasks:propose", "local_task_drafter"):
            return 1
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        rights = instance.read_employee_access(employee_id)
        if rights != {"capabilities": ["company:read", "goals:read"],
                      "tools": ["local_company_reader"]}:
            return 1
        instance.set_employee_inactive(employee_id)
        if instance.read_employee_access(employee_id) != {"capabilities": [], "tools": []}:
            return 1
        instance.restore_employee_draft(employee_id)
        if instance.is_employee_allowed(employee_id, "company:read"):
            return 1
        # Stage 18: the EXE itself checks local-model registry persistence. No
        # AI weights/executable are downloaded or started in this self-test.
        from desktop.model_runtime import ModelConfig
        gguf = Path(directory) / "format-only.gguf"
        gguf.write_bytes(b"GGUF\x03\x00\x00\x00")
        config = ModelConfig("Stage18 engine", "llama_cpp", str(Path(sys.executable).resolve()), str(gguf), 16)
        model_id = instance.add_local_model(config)
        second = instance.add_local_model(ModelConfig("Embedded", "llamafile", str(Path(sys.executable).resolve()), "", 24))
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.list_local_models()
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if [r["name"] for r in instance.list_local_models()] != ["Stage18 engine", "Embedded"]:
            return 1
        instance.update_local_model(model_id, ModelConfig("Stage18 updated", "llama_cpp", str(Path(sys.executable).resolve()), str(gguf), 32))
        if instance.read_local_model(model_id)["max_tokens"] != 32:
            return 1
        instance.delete_local_model(second)
        if not gguf.is_file() or len(instance.list_local_models()) != 1:
            return 1
        # Stage 19: compiled EXE can exercise per-employee model assignment and
        # persistent invocation audit even without installing a real local LLM.
        instance.set_employee_model(employee_id, model_id)
        call_id, selected_config = instance.begin_employee_model_call(employee_id, "local exe audit")
        if selected_config.name != "Stage18 updated":
            return 1
        instance.finish_employee_model_call(call_id, "success", output_chars=5, duration_ms=12)
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_employee_model(employee_id)["model_id"] != model_id:
            return 1
        calls = instance.list_employee_model_calls(employee_id)
        if len(calls) != 1 or calls[0]["status"] != "success" or calls[0]["output_chars"] != 5:
            return 1
        try:
            instance.delete_local_model(model_id)
            return 1
        except ValueError:
            pass
        # Stage 20: the EXE itself checks the chief role gate and audit persistence
        # using a temporary local model registry (no inference or network access).
        chief_id = instance.add_employee_draft("exe_chief_stage20", "EXE 총괄 AI")
        instance.assign_reporting_line(chief_id, "ceo")
        instance.set_employee_model(chief_id, model_id)
        profile = instance.read_chief_profile()
        if profile is None or profile["employee_id"] != chief_id or profile["model_id"] != model_id:
            return 1
        try:
            instance.begin_employee_model_call(employee_id, "not a CEO", required_tier="ceo")
            return 1
        except ValueError:
            pass
        chief_call_id, chief_model = instance.begin_employee_model_call(chief_id, "local chief gate", required_tier="ceo")
        if chief_model.name != "Stage18 updated":
            return 1
        instance.finish_employee_model_call(chief_call_id, "success", output_chars=7, duration_ms=18)
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_chief_profile()["employee_id"] != chief_id or instance.list_employee_model_calls(chief_id)[0]["status"] != "success":
            return 1
        # Stage 21: compiled EXE self-test performs an authorized local snapshot.
        try:
            instance.read_chief_company_status()
            return 1  # must deny by default even to an active CEO
        except AuthenticationError:
            pass
        instance.save_employee_access(chief_id, ["company:read"], ["local_company_reader"])
        view = instance.read_chief_company_status()
        if view["company"]["name"] != "EXE company" or view["goals_authorized"]:
            return 1
        status_goal = instance.add_goal("EXE 조회 목표")
        instance.save_employee_access(chief_id, ["company:read", "goals:read"],
                                     ["local_company_reader", "local_goals_reader"])
        from desktop.company_status import chief_query_with_status
        composed = chief_query_with_status(instance, "회사 상황?")
        if "EXE 조회 목표" not in composed or "EXE company" not in composed:
            return 1
        if len(instance.list_employee_model_calls(chief_id)) != 1:
            return 1  # lookup is never a hidden LLM call
        instance.logout()
        instance = LocalStore(path)
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_chief_company_status()["goal_total"] != 1:
            return 1
        instance.delete_goal(status_goal)
        instance.save_employee_access(chief_id, [], [])
        try:
            instance.read_chief_company_status()
            return 1
        except AuthenticationError:
            pass
        instance.set_employee_model(chief_id, None)
        instance.unassign_reporting_line(chief_id)
        # Only the disposable self-test DB is cleared; never delete real user history.
        with instance._connect() as con:
            con.execute("DELETE FROM ai_model_call_history WHERE employee_id=?", (chief_id,))
            con.execute("DELETE FROM ai_employee_profiles WHERE id=?", (chief_id,))
        instance.set_employee_model(employee_id, None)
        if instance.read_employee_model(employee_id) is not None or len(instance.list_employee_model_calls(employee_id)) != 1:
            return 1
        instance.delete_local_model(model_id)
        # Only the disposable self-test DB is cleaned up using direct SQL.
        # Audit records intentionally protect employee deletion in real user DBs.
        with instance._connect() as con:
            con.execute("DELETE FROM ai_model_call_history WHERE employee_id=?", (employee_id,))
            con.execute("DELETE FROM ai_employee_profiles WHERE id=?", (employee_id,))
        instance.delete_department(department_id)
        for identifier in (rank_id, job_id, role_id):
            instance.delete_designation(identifier)
        if instance.list_designations():
            return 1
        # Stage24: built EXE verifies local automatic assignment, history,
        # fail-closed account access and reopen with no subprocess or network.
        route_dept = instance.add_department("EXE routing dept")
        route_job = instance.add_designation("job", "EXE routing job")
        worker = instance.add_employee_draft("exe_route24", "EXE 자동 배정 직원",
                                             department_id=route_dept, job_id=route_job)
        routed_task = instance.add_task("EXE assign only")
        instance.save_task_requirements(routed_task,route_dept,route_job)
        result = instance.auto_assign_task(routed_task)
        if result["employee_id"] != worker or not result["changed"]:
            return 1
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.read_task_routing(routed_task)
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_task_routing(routed_task)["employee_id"] != worker:
            return 1
        if instance.auto_assign_task(routed_task)["changed"]:
            return 1
        instance.set_employee_inactive(worker)
        if instance.read_task_routing(routed_task)["employee_id"] is not None:
            return 1
        if [x["action"] for x in instance.list_task_assignment_events(routed_task)] != ["auto_assigned", "employee_inactive"]:
            return 1
        # Stage25: owner-only priority edit, audit and fresh DB reopen.
        if instance.read_task(routed_task)["priority"] != "normal":
            return 1
        if not instance.set_task_priority(routed_task, "urgent"):
            return 1
        if instance.set_task_priority(routed_task, "urgent"):
            return 1
        instance.logout()
        instance = LocalStore(path)
        try:
            instance.list_task_priority_events(routed_task)
            return 1
        except AuthenticationError:
            pass
        instance.login("exe_tester", "test-password-long-2026")
        if instance.read_task(routed_task)["priority"] != "urgent":
            return 1
        if len(instance.list_task_priority_events(routed_task)) != 1:
            return 1
        if instance.list_tasks()[0]["id"] != routed_task:
            return 1
        instance.delete_task(routed_task)
        if instance.list_tasks():
            return 1
        # Stage33: EXE self-test exercises draft-only automatic generation,
        # explicit approval, persistence and absence of automatic model runs.
        auto_goal = instance.add_goal('EXE stage33 owner goal')
        instance.update_goal(auto_goal, 'EXE stage33 owner goal', '', 'active')
        proposal_ids = instance.scan_autonomous_task_proposals()['created_ids']
        if len(proposal_ids) != 1 or instance.list_tasks():
            return 1
        # Stage34: real packaged process checks offline deterministic ranking.
        assessments = instance.list_task_proposal_assessments()
        if (len(assessments) != 1 or assessments[0]['proposal_id'] != proposal_ids[0]
                or assessments[0]['feasibility'] != 'needs_plan'
                or assessments[0]['recommended_priority'] != 'low'
                or assessments[0]['score'] != 35):
            return 1
        if instance.analyze_task_proposals()['unchanged'] != 1:
            return 1
        auto_task = instance.approve_autonomous_task_proposal(proposal_ids[0])
        if not auto_task or instance.read_task(auto_task)['status'] != 'todo':
            return 1
        if instance.list_task_runs() or instance.scan_autonomous_task_proposals()['created_ids']:
            return 1
        instance.logout()
        instance = LocalStore(path)
        instance.login('exe_tester', 'test-password-long-2026')
        if instance.list_autonomous_task_proposals()[0]['approved_task_id'] != auto_task:
            return 1
        if len(instance.list_task_proposal_assessment_history(proposal_ids[0])) != 1:
            return 1
        if instance.read_task(auto_task)['priority'] != 'normal':
            return 1  # Stage34 suggestion must not auto-apply to approved tasks.
        # Stage35: executable's own SQLite migration, review-only draft and
        # owner-gated creation of ordered unassigned todo tasks (no model run).
        complex_goal = instance.add_goal('EXE stage35 goal')
        instance.update_goal(complex_goal, 'EXE stage35 goal', '', 'active')
        complex_plan = instance.add_work_plan(complex_goal, 'EXE stage35 complex plan', '',
            [f'Offline step {n}' for n in range(1, 7)], 'ready')
        breakdown = instance.generate_task_breakdown(complex_plan)
        if len(instance.read_task_breakdown(breakdown)['items']) != 6:
            return 1
        if instance.list_tasks(complex_plan):
            return 1
        ids = instance.apply_task_breakdown(breakdown)
        if ids is None or len(ids) != 6 or instance.list_task_runs():
            return 1
        instance.logout()
        instance = LocalStore(path)
        instance.login('exe_tester', 'test-password-long-2026')
        if instance.read_task_breakdown(breakdown)['status'] != 'applied':
            return 1
        if instance.task_dependency_readiness(ids[1])['pending_ids'] != [ids[0]]:
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
