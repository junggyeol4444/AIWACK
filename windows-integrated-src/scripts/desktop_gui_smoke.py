"""Real Tk widget buttons and persisted owner login in two real GUI lifetimes."""
from pathlib import Path
import tempfile
import sys
import time
import tkinter as tk

from desktop.app import AIWACKWindow
from desktop.storage import LocalStore


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aiwack-gui-") as directory:
        path = Path(directory) / "gui.sqlite3"
        root = tk.Tk()
        try:
            app = AIWACKWindow(root, LocalStore(path))
            root.update()
            assert root.winfo_exists()
            assert "AIWACK" in root.title()
            assert not hasattr(app, "tabs"), "Dashboard should not appear before first setup"
            app.account_name.set("owner_test")
            app.account_password.set("my-strong-password-2026")
            app.password_confirm.set("not-matching")
            app.auth_button.invoke()
            root.update()
            assert not app.store.has_owner()
            app.password_confirm.set("my-strong-password-2026")
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert len(app.roadmap_tree.get_children()) == 100
            assert app.tabs.index("end") >= 22, "stage32 detection must be a native notebook view"
            app.tabs.select(3)
            root.update()
            for key, title in (("overview", "회사 현황"), ("departments", "조직·직원"),
                               ("tasks", "업무·프로젝트"), ("business", "사업·상품"),
                               ("finance", "재무·매출"), ("permissions", "승인·권한"),
                               ("settings", "운영·설정")):
                app.admin_navigation[key].invoke()
                root.update()
                assert app.current_admin_section == key
                assert app.admin_title.get() == title
            assert "미구현" in app.admin_state.get()
            app.admin_navigation["permissions"].invoke()
            assert "owner" in app.admin_realtime.get()
            app.admin_navigation["overview"].invoke()
            assert "SQLite 정상" in app.admin_realtime.get()
            app.tabs.select(4)
            app.company_name.set("AIWACK 실사 회사")
            app.company_description.set("GUI에서 저장한 회사 설명")
            app.company_mission.set("윈도우 앱에서 실제 업무 관리")
            app.company_save_button.invoke()
            root.update()
            assert app.store.read_company()["name"] == "AIWACK 실사 회사"
            app.goal_title.set("창에서 직접 목표 추가")
            app.goal_detail.set("상태 변경/삭제도 확인")
            app.goal_add_button.invoke()
            root.update()
            assert len(app.goal_tree.get_children()) == 1
            goal_id = int(app.goal_tree.get_children()[0])
            app.goal_tree.selection_set(str(goal_id))
            root.update()
            app.goal_title.set("업데이트 된 목표")
            app.goal_status.set("active")
            app.goal_update_button.invoke()
            root.update()
            assert app.store.list_goals()[0]["title"] == "업데이트 된 목표"
            assert app.store.list_goals()[0]["status"] == "active"
            # Stage 22: actual owner-only plan form, ordered steps and data persistence.
            app.tabs.select(13)
            root.update()
            assert app.work_plan_goal_combo.get()
            app.work_plan_title.set("GUI 회사 업무 계획")
            app.work_plan_description.set("출시 전 준비 순서")
            app.work_plan_steps.insert("1.0", "시장 분석\n검수 및 승인")
            app.work_plan_add_button.invoke()
            root.update()
            assert len(app.store.list_work_plans()) == 1, app.work_plan_feedback.get()
            plan_id = app.store.list_work_plans()[0]["id"]
            app.work_plan_tree.selection_set(str(plan_id))
            root.update()
            app.work_plan_title.set("GUI 수정된 회사 업무 계획")
            app.work_plan_status.set("ready")
            app.work_plan_steps.delete("1.0", "end")
            app.work_plan_steps.insert("1.0", "준비 순서\n최종 검토\n승인")
            app.work_plan_update_button.invoke()
            root.update()
            assert app.store.read_work_plan(plan_id)["title"] == "GUI 수정된 회사 업무 계획"
            assert app.store.read_work_plan(plan_id)["steps"] == ["준비 순서", "최종 검토", "승인"]
            assert app.store.read_work_plan(plan_id)["status"] == "ready"
            # Stage 23: create/edit/status lifecycle with actual Tk buttons and linked plan.
            app.tabs.select(14)
            root.update()
            app.task_title.set("GUI 신규 업무")
            app.task_description.set("사람이 입력한 확인 업무")
            plan_option = next(k for k, v in app.task_plan_map.items() if v == plan_id)
            app.task_plan.set(plan_option)
            app.task_add_button.invoke()
            root.update()
            assert len(app.store.list_tasks()) == 1, app.task_feedback.get()
            task_id = app.store.list_tasks()[0]["id"]
            assert app.store.read_task(task_id)["status"] == "todo"
            app.task_tree.selection_set(str(task_id))
            root.update()
            # Stage 25: priority saved via the actual Tk button and reflected in tree.
            assert app.task_priority.get() == "normal"
            app.task_priority.set("urgent")
            app.task_priority_button.invoke()
            root.update()
            assert app.store.read_task(task_id)["priority"] == "urgent"
            assert app.task_tree.item(str(task_id), "values")[-1] == "urgent"
            assert len(app.store.list_task_priority_events(task_id)) == 1
            app.task_title.set("GUI 수정된 업무")
            app.task_update_button.invoke()
            root.update()
            assert app.store.read_task(task_id)["title"] == "GUI 수정된 업무"
            app.task_status.set("in_progress")
            app.task_status_button.invoke()
            root.update()
            assert app.store.read_task(task_id)["status"] == "in_progress"
            app.task_status.set("done")
            app.task_status_button.invoke()
            root.update()
            assert app.store.read_task(task_id)["status"] == "done"
            assert app.store.read_task(task_id)["priority"] == "urgent"
            assert len(app.store.list_task_status_events(task_id)) == 3
            # Task status updates track records only; no subprocess is launched.
            # Stage 12: actual native form buttons and SQLite CRUD.
            app.tabs.select(5)
            app.department_name.set("시장조사부")
            app.department_description.set("시장분석 및 기회 탐색")
            app.department_add_button.invoke()
            root.update()
            assert len(app.department_tree.get_children()) == 1
            department_id = str(app.store.list_departments()[0]["id"])
            app.department_tree.selection_set(department_id)
            root.update()
            app.department_name.set("시장조사·분석부")
            app.department_update_button.invoke()
            root.update()
            assert app.store.list_departments()[0]["name"] == "시장조사·분석부"
            app.admin_navigation["departments"].invoke()
            assert "1개" in app.admin_realtime.get()
            # Stage 13: exercise all three catalog classifications via real Tk buttons.
            app.tabs.select(6)
            root.update()
            for kind, label in (("rank", "팀장"), ("job", "시장조사"), ("role", "품질검수")):
                app.designation_kind.set(kind)
                app.designation_name.set(label)
                app.designation_description.set("직접 입력한 정의")
                app.designation_add_button.invoke()
                root.update()
            assert len(app.designation_tree.get_children()) == 3
            selected_designation = str(app.store.list_designations("role")[0]["id"])
            app.designation_tree.selection_set(selected_designation)
            root.update()
            app.designation_name.set("최종 품질검수")
            app.designation_update_button.invoke()
            root.update()
            assert app.store.list_designations("role")[0]["name"] == "최종 품질검수"
            app.admin_navigation["departments"].invoke()
            assert "3개" in app.admin_realtime.get()
            assert "AI 직원 정보 0건" in app.admin_realtime.get()
            assert app.store.list_employee_records() == []
            # Stage 15: actual Tk buttons: create, update, deactivate, restore.
            app.tabs.select(7)
            root.update()
            assert app.employee_tree.get_children() == ()
            app.employee_key.set("gui_employee_001")
            app.employee_name.set("실사 직원")
            app.employee_description.set("첫 저장")
            for kind, value in (("department", app.store.list_departments()[0]),
                                ("rank", app.store.list_designations("rank")[0]),
                                ("job", app.store.list_designations("job")[0]),
                                ("role", app.store.list_designations("role")[0])):
                app.employee_links[kind].set(f"{value['id']} · {value['name']}")
            app.employee_create_button.invoke()
            root.update()
            employees = app.store.list_employee_records()
            assert len(employees) == 1
            eid = employees[0]["id"]
            assert employees[0]["department_id"] is not None
            app.employee_tree.selection_set(str(eid))
            root.update()
            app.employee_name.set("수정된 실사 직원")
            app.employee_update_button.invoke()
            root.update()
            assert app.store.read_employee_record(eid)["display_name"] == "수정된 실사 직원"
            from tkinter import messagebox
            previous_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app.employee_inactive_button.invoke()
                assert app.store.read_employee_record(eid)["lifecycle"] == "draft"
                messagebox.askyesno = lambda *args, **kwargs: True
                app.employee_inactive_button.invoke()
            finally:
                messagebox.askyesno = previous_confirm
            assert app.store.read_employee_record(eid)["lifecycle"] == "inactive"
            app.employee_restore_button.invoke()
            root.update()
            assert app.store.read_employee_record(eid)["lifecycle"] == "draft"
            app.store.set_employee_inactive(eid)
            app.reload_employees(eid)
            # Stage 16: real native hierarchy form, button actions and tree nesting.
            chief = app.store.add_employee_draft("hier_ceo", "총괄 AI")
            head = app.store.add_employee_draft("hier_head", "시장조사 부서장",
                                                department_id=int(department_id))
            member = app.store.add_employee_draft("hier_member", "시장조사 직원",
                                                  department_id=int(department_id))
            app.tabs.select(8)
            root.update()
            app.reload_hierarchy()
            app.hierarchy_tree.selection_set(str(chief))
            root.update()
            app.hierarchy_tier.set("ceo")
            app.refresh_hierarchy_managers()
            app.hierarchy_assign_button.invoke()
            root.update()
            assert app.store.list_reporting_lines()[0]["employee_id"] == chief
            app.hierarchy_tree.selection_set(str(head))
            root.update()
            app.hierarchy_tier.set("department_head")
            app.refresh_hierarchy_managers()
            app.hierarchy_manager.set(f"{chief} · 총괄 AI")
            app.hierarchy_assign_button.invoke()
            root.update()
            assert app.hierarchy_tree.parent(str(head)) == str(chief)
            app.hierarchy_tree.selection_set(str(member))
            root.update()
            app.hierarchy_tier.set("staff")
            app.refresh_hierarchy_managers()
            app.hierarchy_manager.set(f"{head} · 시장조사 부서장")
            app.hierarchy_assign_button.invoke()
            root.update()
            assert app.hierarchy_tree.parent(str(member)) == str(head)
            app.hierarchy_tree.selection_set(str(chief))
            root.update()
            from tkinter import messagebox
            confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: True
                app.hierarchy_clear_button.invoke()
                root.update()
                assert "해제 실패" in app.hierarchy_feedback.get()
            finally:
                messagebox.askyesno = confirm
            assert len(app.store.list_reporting_lines()) == 3
            # Stage 17: real local Tk choices, permission/tool checkboxes and save buttons.
            app.tabs.select(9)
            root.update()
            entries = list(app.access_employee_combo["values"])
            selected = next(x for x in entries if x.startswith(f"{member} · "))
            app.access_employee.set(selected)
            app.load_employee_access()
            assert not any(v.get() for v in app.access_cap_vars.values())
            app.access_cap_vars["company:read"].set(True)
            app.access_tool_vars["local_company_reader"].set(True)
            app.access_save_button.invoke()
            root.update()
            assert "저장 완료" in app.access_feedback.get()
            assert app.store.is_employee_allowed(member, "company:read", "local_company_reader")
            app.access_tool_vars["local_goals_reader"].set(True)  # lacks goals permission
            app.access_save_button.invoke()
            assert "저장 실패" in app.access_feedback.get()
            assert app.store.read_employee_access(member)["tools"] == ["local_company_reader"]
            app.access_tool_vars["local_goals_reader"].set(False)
            # Stage 18: real Tk CRUD and explicit test invoking a real LOCAL process.
            # This tiny CLI is not an AI model; it verifies the execution pathway only.
            executable = Path(directory) / "local-model-fixture"
            executable.write_text("#!/usr/bin/env python3\nimport sys\nprint('LOCAL_UI_OK ' + ' '.join(sys.argv[1:]))\n", encoding="utf-8")
            executable.chmod(0o700)
            gguf = Path(directory) / "test.gguf"
            gguf.write_bytes(b"GGUF\x03\x00\x00\x00")
            app.quick_navigation.set("로컬 AI 모델")
            app._jump_to_tab()
            root.update()
            assert app.tabs.index(app.tabs.select()) == 10
            app.model_name.set("로컬 1호 모델")
            app.model_backend.set("llama_cpp")
            app.model_executable.set(str(executable))
            app.model_file.set(str(gguf))
            app.model_tokens.set("8")
            app.model_add_button.invoke()
            root.update()
            assert len(app.store.list_local_models()) == 1
            model_id = app.store.list_local_models()[0]["id"]
            app.model_tree.selection_set(str(model_id))
            root.update()
            app.model_name.set("수정된 모델")
            app.model_update_button.invoke()
            root.update()
            assert app.store.read_local_model(model_id)["name"] == "수정된 모델"
            app.model_verify_button.invoke()
            root.update()
            assert "검사 통과" in app.model_feedback.get()
            app.model_prompt.set("안녕, 로컬 모델")
            app.model_run_button.invoke()
            started = time.monotonic()
            while app._model_running and time.monotonic() - started < 8:
                root.update()
                time.sleep(.05)
            root.update()
            assert not app._model_running, "local subprocess did not finish"
            assert "LOCAL_UI_OK" in app.model_result.get("1.0", "end")
            assert "로컬 실행파일 응답 완료" in app.model_feedback.get()
            # Stage 19: actual owner-only native widgets: assign employee model,
            # manual local invocation, metadata-only durable history.
            app.tabs.select(11)
            root.update()
            app.employee_model_employee.set(next(x for x in app.employee_model_employee_combo["values"]
                                                  if x.startswith(f"{member} · ")))
            app.load_employee_model()
            assert not app.store.read_employee_model(member)
            app.employee_model_model.set(next(x for x in app.employee_model_model_combo["values"]
                                               if x.startswith(f"{model_id} · ")))
            app.employee_model_save_button.invoke()
            root.update()
            assert app.store.read_employee_model(member)["model_id"] == model_id
            assert app.store.list_employee_model_calls(member) == []  # assignment never starts a program
            app.employee_model_prompt.set("직원 로컬 수동 호출")
            app.employee_model_run_button.invoke()
            started = time.monotonic()
            while app._model_running and time.monotonic() - started < 8:
                root.update()
                time.sleep(.05)
            root.update()
            assert not app._model_running, "stage19 local process did not finish"
            assert "LOCAL_UI_OK" in app.employee_model_result.get("1.0", "end")
            assert "호출 이력 저장" in app.employee_model_feedback.get()
            assert app.store.list_employee_model_calls(member)[0]["status"] == "success"
            assert len(app.employee_model_history.get_children()) == 1
            # Stage 20: CEO-only basic chat, real local runner, visible response.
            app.tabs.select(12)
            root.update()
            app.refresh_chief_state()
            assert "미배정" in app.chief_state.get()
            app.chief_input.insert("1.0", "unassigned chief test")
            app.chief_run_button.invoke()
            root.update()
            assert "발송 실패" in app.chief_feedback.get()
            assert not app.store.list_employee_model_calls(chief)
            app.store.set_employee_model(chief, model_id)
            app.refresh_chief_state()
            assert "수정된 모델" in app.chief_state.get()
            # Stage21: the real GUI must deny data lookup without chief grants.
            app.chief_status_button.invoke()
            root.update()
            assert "조회 실패" in app.chief_feedback.get()
            assert "회사 현황" not in app.chief_transcript.get("1.0", "end")
            app.store.save_employee_access(chief,
                ["company:read", "goals:read"],
                ["local_company_reader", "local_goals_reader"])
            history_before_status = len(app.store.list_employee_model_calls(chief))
            app.chief_status_button.invoke()
            root.update()
            status_transcript = app.chief_transcript.get("1.0", "end")
            assert "AIWACK 실사 회사" in status_transcript
            assert "시장조사·분석부" in status_transcript
            assert "업데이트 된 목표" in status_transcript
            assert len(app.store.list_employee_model_calls(chief)) == history_before_status, "status lookup must not launch a model"
            app.chief_include_status.set(True)  # opt-in only, never implicit
            private_prompt = "STAGE20_GUI_PRIVATE_77Q"
            app.chief_input.delete("1.0", "end")
            app.chief_input.insert("1.0", private_prompt)
            app.chief_run_button.invoke()
            started = time.monotonic()
            while app._model_running and time.monotonic() - started < 8:
                root.update()
                time.sleep(.05)
            root.update()
            assert not app._model_running, "stage 20 chief local runner did not finish"
            assert "LOCAL_UI_OK" in app.chief_transcript.get("1.0", "end")
            assert "AIWACK 실사 회사" in app.chief_transcript.get("1.0", "end")
            assert "회사 데이터 시작" in app.chief_transcript.get("1.0", "end")
            assert "응답 완료" in app.chief_feedback.get()
            assert app.store.list_employee_model_calls(chief)[0]["status"] == "success"
            assert private_prompt.encode() not in path.read_bytes()
            app.tabs.select(1)
            app.note.set("PC 앱 로그인 뒤 저장 성공")
            app.save_button.invoke()
            root.update()
            assert "저장 완료" in app.feedback.get()
            assert app.store.read_note() == "PC 앱 로그인 뒤 저장 성공"
            app.sign_out()
            root.update()
            assert not app.store.is_authenticated
            from desktop.storage import AuthenticationError
            try:
                app.show_admin_section("overview")
            except AuthenticationError:
                pass
            else:
                raise AssertionError("signed-out admin navigation must be refused")
            app.account_name.set("owner_test")
            app.account_password.set("wrong_password")
            app.auth_button.invoke()
            root.update()
            assert not app.store.is_authenticated
            app.account_password.set("my-strong-password-2026")
            app.auth_button.invoke()
            root.update()
            assert app.store.is_authenticated
            assert app.note.get() == "PC 앱 로그인 뒤 저장 성공"
        finally:
            root.destroy()
        root2 = tk.Tk()
        try:
            app2 = AIWACKWindow(root2, LocalStore(path))
            root2.update()
            assert not app2.store.is_authenticated
            assert not hasattr(app2, "tabs")
            app2.account_name.set("owner_test")
            app2.account_password.set("my-strong-password-2026")
            app2.auth_button.invoke()
            root2.update()
            assert app2.note.get() == "PC 앱 로그인 뒤 저장 성공"
            app2.tabs.select(12)
            root2.update()
            app2.refresh_chief_state()
            assert "수정된 모델" in app2.chief_state.get()
            assert not app2.chief_transcript.get("1.0", "end").strip(), "chat body must not persist"
            assert not app2.chief_include_status.get(), "company context opt-in must reset on relogin"
            app2.chief_status_button.invoke()
            root2.update()
            assert "AIWACK 실사 회사" in app2.chief_transcript.get("1.0", "end")
            assert app2.store.list_employee_model_calls(chief)[0]["status"] == "success"
            app2.tabs.select(4)
            assert app2.company_name.get() == "AIWACK 실사 회사"
            assert app2.store.list_goals()[0]["title"] == "업데이트 된 목표"
            # A referenced goal may not be removed until the plan is removed.
            from desktop.storage import AuthenticationError
            try:
                app2.store.delete_goal(goal_id)
            except ValueError:
                pass
            else:
                raise AssertionError("goal with plans must be protected")
            # Stage23: verified after full program shutdown/re-login.
            app2.tabs.select(14)
            root2.update()
            assert len(app2.task_tree.get_children()) == 1
            assert app2.store.read_task(task_id)["status"] == "done"
            assert app2.store.read_task(task_id)["priority"] == "urgent"
            assert len(app2.store.list_task_priority_events(task_id)) == 1
            assert len(app2.store.list_task_status_events(task_id)) == 3
            app2.task_tree.selection_set(str(task_id))
            root2.update()
            # Finished tasks need explicit owner reopen before editing or deletion.
            app2.task_status.set("todo")
            app2.task_status_button.invoke()
            root2.update()
            assert app2.store.read_task(task_id)["status"] == "todo"
            assert len(app2.store.list_task_status_events(task_id)) == 4
            # Stage26: real GUI buttons, status guard, durable audit and restart.
            prereq_id = app2.store.add_task("GUI 선행 작업")
            app2.tabs.select(16)
            root2.update()
            app2.dependency_refresh_button.invoke()
            root2.update()
            app2.dependency_task.set(next(k for k,v in app2.dependency_task_map.items() if v == task_id))
            app2.dependency_prerequisite.set(next(k for k,v in app2.dependency_task_map.items() if v == prereq_id))
            app2.dependency_add_button.invoke()
            root2.update()
            assert len(app2.dependency_tree.get_children()) == 1, app2.dependency_feedback.get()
            assert not app2.store.task_dependency_readiness(task_id)["ready"]
            app2.tabs.select(14)
            root2.update()
            app2.task_tree.selection_set(str(task_id))
            root2.update()
            app2.task_status.set("in_progress")
            app2.task_status_button.invoke()
            root2.update()
            assert app2.store.read_task(task_id)["status"] == "todo"
            assert "선행 업무" in app2.task_feedback.get()
            app2.store.set_task_status(prereq_id, "in_progress")
            app2.store.set_task_status(prereq_id, "done")
            assert app2.store.task_dependency_readiness(task_id)["ready"]
            app2.tabs.select(16)
            root2.update()
            app2.load_task_dependencies()
            assert app2.dependency_tree.item(str(prereq_id), "values")[-1] == "완료"
            app2.dependency_tree.selection_set(str(prereq_id))
            app2.dependency_remove_button.invoke()
            root2.update()
            assert not app2.store.list_task_dependencies(task_id)
            assert [x["action"] for x in app2.store.list_task_dependency_events(task_id)] == ["added", "removed"]
            app2.store.set_task_status(prereq_id, "todo")
            app2.store.delete_task(prereq_id)
            assert len(app2.store.list_tasks()) == 1
            app2.tabs.select(14)
            app2.reload_tasks(task_id)
            root2.update()
            # Stage24: actual GUI chooses an existing employee draft without starting an AI.
            app2.tabs.select(15)
            root2.update()
            option = next(k for k,v in app2.task_route_task_map.items() if v == task_id)
            app2.task_route_task.set(option)
            app2.load_task_routing()
            dep_option = next(k for k,v in app2.task_route_dept_map.items() if v == int(department_id))
            app2.task_route_department.set(dep_option)
            app2.task_route_save_button.invoke()
            root2.update()
            assert app2.store.read_task_routing(task_id)["department_id"] == int(department_id)
            app2.task_route_assign_button.invoke()
            root2.update()
            assert app2.store.read_task_routing(task_id)["employee_id"] == member
            assert "배정 완료" in app2.task_route_feedback.get()
            assert len(app2.task_route_events.get_children()) == 1
            app2.task_route_assign_button.invoke()
            assert len(app2.task_route_events.get_children()) == 1, "repeated click is idempotent"
            app2.task_route_clear_button.invoke()
            root2.update()
            assert app2.store.read_task_routing(task_id)["employee_id"] is None
            assert len(app2.task_route_events.get_children()) == 2
            app2.task_route_assign_button.invoke()
            assert app2.store.read_task_routing(task_id)["employee_id"] == member
            assert len(app2.task_route_events.get_children()) == 3
            # Account logout invalidates every owner-only routing API, too.
            app2.tabs.select(14)
            root2.update()
            app2.task_tree.selection_set(str(task_id))
            root2.update()
            from tkinter import messagebox
            confirm_task = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.task_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_tasks()) == 1
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.task_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_tasks()) == 0
            finally:
                messagebox.askyesno = confirm_task
            app2.tabs.select(13)
            root2.update()
            assert len(app2.work_plan_tree.get_children()) == 1
            assert app2.store.read_work_plan(plan_id)["steps"] == ["준비 순서", "최종 검토", "승인"]
            from tkinter import messagebox
            confirm_plan = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.work_plan_tree.selection_set(str(plan_id))
                app2.work_plan_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_work_plans()) == 1
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.work_plan_delete_button.invoke()
                root2.update()
                assert app2.store.list_work_plans() == []
            finally:
                messagebox.askyesno = confirm_plan
            app2.tabs.select(4)
            # The delete UI requires explicit confirmation; stub only the dialog.
            from tkinter import messagebox
            original_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.goal_tree.selection_set(app2.goal_tree.get_children()[0])
                app2.goal_delete_button.invoke()
                root2.update()
                assert app2.store.list_goals() == []
            finally:
                messagebox.askyesno = original_confirm
            app2.tabs.select(5)
            assert app2.store.list_departments()[0]["name"] == "시장조사·분석부"
            # No confirmation => no deletion.
            from tkinter import messagebox
            saved_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.department_tree.selection_set(str(app2.store.list_departments()[0]["id"]))
                app2.department_delete_button.invoke()
                assert len(app2.store.list_departments()) == 1
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.department_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_departments()) == 1  # employee FK protects data
            finally:
                messagebox.askyesno = saved_confirm
            app2.tabs.select(6)
            assert len(app2.store.list_designations()) == 3
            assert app2.store.list_designations("role")[0]["name"] == "최종 품질검수"
            from tkinter import messagebox
            saved_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.designation_tree.selection_set(
                    str(app2.store.list_designations("role")[0]["id"]))
                app2.designation_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_designations()) == 3
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.designation_delete_button.invoke()
                root2.update()
                assert len(app2.store.list_designations()) == 3  # employee FK protects role
            finally:
                messagebox.askyesno = saved_confirm
            app2.tabs.select(7)
            root2.update()
            assert len(app2.employee_tree.get_children()) == 4
            assert app2.store.read_employee_record(eid)["lifecycle"] == "inactive"
            assert app2.store.read_employee_record(eid)["display_name"] == "수정된 실사 직원"
            app2.tabs.select(8)
            root2.update()
            assert len(app2.store.list_reporting_lines()) == 3
            assert app2.hierarchy_tree.parent(str(member)) == str(head)
            assert app2.hierarchy_tree.parent(str(head)) == str(chief)
            app2.tabs.select(9)
            root2.update()
            app2.access_employee.set(next(x for x in app2.access_employee_combo["values"]
                                         if x.startswith(f"{member} · ")))
            app2.load_employee_access()
            assert app2.access_cap_vars["company:read"].get()
            assert app2.access_tool_vars["local_company_reader"].get()
            confirm_access = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.access_revoke_button.invoke()
                assert app2.store.is_employee_allowed(member, "company:read")
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.access_revoke_button.invoke()
                assert not app2.store.is_employee_allowed(member, "company:read")
            finally:
                messagebox.askyesno = confirm_access
            # Stage 19: model bindings and privacy-preserving invocation history survive reopening.
            app2.tabs.select(11)
            root2.update()
            app2.employee_model_employee.set(next(x for x in app2.employee_model_employee_combo["values"]
                                                   if x.startswith(f"{member} · ")))
            app2.load_employee_model()
            assert app2.store.read_employee_model(member)["model_id"] == model_id
            assert app2.store.list_employee_model_calls(member)[0]["status"] == "success"
            assert len(app2.employee_model_history.get_children()) == 1
            # Unassign model while preserving audit and then delete model registry.
            app2.employee_model_clear_button.invoke()
            root2.update()
            assert app2.store.read_employee_model(member) is None
            assert len(app2.store.list_employee_model_calls(member)) == 1
            # Stage20 chief also has a persistent assignment: release it before registry deletion.
            app2.store.set_employee_model(chief, None)
            assert len(app2.store.list_employee_model_calls(chief)) == 1
            # Model registry persists across close/login; deletion never touches GGUF.
            app2.tabs.select(10)
            root2.update()
            assert [x["name"] for x in app2.store.list_local_models()] == ["수정된 모델"]
            assert len(app2.model_tree.get_children()) == 1
            app2.model_tree.selection_set(app2.model_tree.get_children()[0])
            root2.update()
            from tkinter import messagebox
            old_confirm = messagebox.askyesno
            try:
                messagebox.askyesno = lambda *args, **kwargs: False
                app2.model_delete_button.invoke()
                assert len(app2.store.list_local_models()) == 1
                messagebox.askyesno = lambda *args, **kwargs: True
                app2.model_delete_button.invoke()
                assert len(app2.store.list_local_models()) == 0
            finally:
                messagebox.askyesno = old_confirm
            assert executable.is_file() and gguf.is_file()
            # Stage27: real Tk button invokes the local CLI for a routed task.
            # Create a fresh task after previous CRUD checks so its protected
            # audit history cannot interfere with the earlier deletion tests.
            from desktop.model_runtime import ModelConfig
            model27=app2.store.add_local_model(ModelConfig('Stage27 local', 'llama_cpp',
                                                            str(executable),str(gguf),8))
            app2.store.set_employee_model(member,model27)
            task27=app2.store.add_task('GUI Stage27 AI draft', 'offline text only')
            app2.store.save_task_requirements(task27,int(department_id),None)
            assert app2.store.auto_assign_task(task27)['employee_id']==member
            app2.tabs.select(17)
            root2.update()
            app2.task_execution_task.set(next(k for k,v in app2.task_execution_map.items() if v==task27))
            app2.load_task_execution()
            assert not app2.store.list_task_runs(task27)
            from tkinter import messagebox
            original_confirm=messagebox.askyesno
            try:
                messagebox.askyesno=lambda *a,**kw:True
                app2.task_execution_run_button.invoke()
            finally:
                messagebox.askyesno=original_confirm
            started=time.monotonic()
            while app2._model_running and time.monotonic()-started < 8:
                root2.update()
                time.sleep(.05)
            root2.update()
            assert not app2._model_running,app2.task_execution_feedback.get()
            assert 'LOCAL_UI_OK' in app2.task_execution_output.get('1.0','end')
            assert app2.store.read_task(task27)['status']=='in_progress'
            assert app2.store.list_task_runs(task27)[0]['status']=='success'
            assert len(app2.task_execution_events.get_children())==1
            assert b'LOCAL_UI_OK' not in path.read_bytes()
            # Stage28: no automatic storage; explicit GUI save and owner review.
            assert app2.store.list_task_artifacts(task27)==[]
            original_confirm=messagebox.askyesno
            try:
                messagebox.askyesno=lambda *a,**kw:True
                app2.save_current_task_draft()
            finally:
                messagebox.askyesno=original_confirm
            artifacts=app2.store.list_task_artifacts(task27)
            assert len(artifacts)==1,app2.task_execution_feedback.get()
            artifact_id=artifacts[0]['id']
            assert 'LOCAL_UI_OK' in app2.store.read_task_artifact(artifact_id)['body']
            app2.tabs.select(18)
            root2.update()
            assert str(artifact_id) in app2.task_artifact_list.get_children()
            app2.task_artifact_list.selection_set(str(artifact_id))
            app2.load_task_artifact()
            assert 'LOCAL_UI_OK' in app2.task_artifact_body.get('1.0','end')
            app2.task_artifact_note.set('관리자 검수 완료')
            original_confirm=messagebox.askyesno
            try:
                messagebox.askyesno=lambda *a,**kw:True
                app2.review_selected_task_artifact('approved')
            finally:
                messagebox.askyesno=original_confirm
            assert app2.store.read_task_artifact(artifact_id)['review_status']=='approved'
            assert app2.store.read_task(task27)['status']=='in_progress'

            check=LocalStore(path)
            check.login('owner_test','my-strong-password-2026')
            assert check.list_task_runs(task27)[0]['status']=='success'
            assert check.read_task(task27)['status']=='in_progress'
            assert check.read_task_artifact(artifact_id)['review_status']=='approved'
            app2.tabs.select(3)
            app2.admin_navigation["permissions"].invoke()
            assert app2.current_admin_section == "permissions"
            assert root2.winfo_exists()
        finally:
            root2.destroy()
    print("PASS: native Tk login, employee creation/edit/deactivate/reactivate, restart, persistence, access grants and revocation, local model registry, employee model assignment and audited explicit process execution, native owner-only chief chat, stage24 task routing, stage25 priority, stage26 dependency and stage27 local task execution and stage28 artifact review GUI")


if __name__ == "__main__":
    main()
