import tempfile, tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog
from desktop.app import AIWACKWindow
from desktop.storage import LocalStore

with tempfile.TemporaryDirectory() as td:
    root=tk.Tk()
    try:
        st=LocalStore(Path(td)/'gui_tool.sqlite3')
        ui=AIWACKWindow(root,st)
        ui.account_name.set('owner')
        ui.account_password.set('native-local-tool-password')
        ui.password_confirm.set('native-local-tool-password')
        ui.submit_setup()
        root.update()
        employee=st.add_employee_draft('gui_tool_staff','GUI 도구 담당')
        st.save_employee_access(employee,['company:read'],['local_company_reader'])
        tool=st.register_ai_tool('local_company_reader','회사 실제 읽기','management','로컬 읽기','company:read')
        rid=st.request_ai_tool_use('gui_read_001',tool,employee,'GUI 실제 읽기')
        st.decide_ai_tool_use(rid,'approved','GUI 소유자 승인')
        # 실제 앱의 도구 승인 탭과 실제 Tk 버튼 객체를 찾는다.
        panel=ui.tool_use_execute_button.master
        notebook=ui.tabs
        for i in range(notebook.index('end')):
            if str(panel).startswith(str(notebook.nametowidget(notebook.tabs()[i]))+'.'):
                notebook.select(i);break
        ui._refresh_tool_use()
        root.update()
        items=ui.tool_use_tree.get_children()
        assert items
        ui.tool_use_tree.selection_set(items[0])
        assert ui.tool_use_execute_button.winfo_viewable()
        messagebox.askyesno=lambda *a,**k:True
        ui.tool_use_execute_button.invoke()
        root.update()
        assert '실제 조회 완료' in ui.tool_use_feedback.get(),ui.tool_use_feedback.get()
        assert len(st.approved_local_read_tool_history())==1
        # 동일 기존 GUI에서 새 Windows 기본 명령 실행 버튼의 실제 위치/클릭.
        from desktop import company_native_diagnostics as native
        st.save_employee_access(employee,['company:read'],
                                ['local_company_reader',native.TOOL_KEY])
        cmd=st.register_ai_tool(native.TOOL_KEY,'Windows 버전','operations',
                                '실제 기본 명령 실행','company:read')
        cmdrid=st.request_ai_tool_use('gui_win_ver_001',cmd,employee,'GUI 명령 실행')
        st.decide_ai_tool_use(cmdrid,'approved','GUI 소유자 승인')
        ui._refresh_tool_use()
        root.update()
        for item in ui.tool_use_tree.get_children():
            if int(ui.tool_use_tree.item(item,'values')[0])==cmdrid:
                ui.tool_use_tree.selection_set(item)
                break
        assert ui.tool_windows_version_button.winfo_viewable()
        assert ui.tool_windows_version_button.winfo_rootx()+ui.tool_windows_version_button.winfo_width() <= root.winfo_rootx()+root.winfo_width()
        assert ui.tool_windows_version_button.winfo_rooty()+ui.tool_windows_version_button.winfo_height() <= root.winfo_rooty()+root.winfo_height()
        old=native._run_windows_version
        try:
            native._run_windows_version=lambda:'Windows GUI test'  # GUI 위치만 검증, 실제 Windows 명령은 별도 테스트.
            ui.tool_windows_version_button.invoke()
            root.update()
            assert '실제 명령 실행 완료' in ui.tool_use_feedback.get(),ui.tool_use_feedback.get()
            assert len(st.approved_windows_version_tool_history())==1
        finally:
            native._run_windows_version=old
        # 관리자 클릭으로 오래된 실행만 취소하고 재실행하지 않는 사용자 흐름.
        recovery_request=st.request_ai_tool_use('gui_win_recovery_002',cmd,employee,'복구 시연')
        st.decide_ai_tool_use(recovery_request,'approved','관리자 복구 확인 시험')
        with st._connect() as con:
            native.initialize(con)
            con.execute("""INSERT INTO aiwack_native_tool_runs
                (request_id,employee_id,tool_key,token,state,created_at)
                VALUES(?,?,?,?, 'running',DATETIME('now','-240 seconds'))""",
                (recovery_request,employee,native.TOOL_KEY,'e'*32))
        ui._refresh_tool_use()
        for item in ui.tool_use_tree.get_children():
            if int(ui.tool_use_tree.item(item,'values')[0])==recovery_request:
                ui.tool_use_tree.selection_set(item)
                break
        root.update()
        assert ui.tool_windows_stale_button.winfo_viewable()
        assert ui.tool_windows_stale_button.winfo_rooty()+ui.tool_windows_stale_button.winfo_height() <= root.winfo_rooty()+root.winfo_height()
        old_prompt=simpledialog.askstring
        try:
            simpledialog.askstring=lambda *a,**k:'다른 창을 확인하고 중단 감사만 취소함'
            ui.tool_windows_stale_button.invoke()
        finally:
            simpledialog.askstring=old_prompt
        root.update()
        assert len(st.approved_windows_tool_recovery_history())==1
        assert '재실행 없음' in ui.tool_use_feedback.get()
        print('TK_NATIVE_WINDOWS_STALE_RECOVERY_BUTTON_SQLITE_PASS')
        print('TK_NATIVE_WINDOWS_COMMAND_BUTTON_ACTUAL_SQLITE_PASS')
        print('TK_NATIVE_APPROVED_TOOL_GUI_ACTUAL_SQLITE_PASS')
    finally:
        root.destroy()
