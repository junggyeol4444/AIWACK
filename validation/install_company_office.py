"""Apply source additions ONLY inside test-branch GitHub runner's extracted ZIP.

The checked-in immutable ZIP on main is unchanged. All edits below are limited to
an ephemeral checkout's extracted Windows/Linux application source and verified.
"""
from __future__ import annotations
import ast
from pathlib import Path
import shutil
import sys


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError('Expected exactly one '+label+' anchor; found '+str(source.count(old)))
    return source.replace(old,new,1)


def apply(project: Path) -> None:
    project = Path(project).resolve(strict=True)
    source_dir = Path(__file__).resolve().parent / 'office_source'
    for section,name in [('desktop','company_operations.py'),('desktop','company_office_gui.py'),('desktop','company_model_connect_ui.py'),
                         ('tests','test_company_operations_center.py'),
                         ('tests','test_company_planning_cockpit.py'),('tests','test_company_model_onboarding.py'),('tests','test_company_chief_handoff.py'),
                         ('scripts','company_office_gui_smoke.py'),
                         ('scripts','company_planning_gui_smoke.py'),('scripts','company_model_setup_gui_smoke.py'),('scripts','company_owner_completion_gui_smoke.py'),('scripts','company_chief_order_gui_smoke.py')]:
        origin = source_dir/section/name
        destination=project/section/name
        if not origin.is_file() or destination.exists():
            raise RuntimeError('Missing test-branch addition or refusing overwrite: '+str(destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin,destination)
    app_path=project/'desktop/app.py'
    src=app_path.read_text(encoding='utf-8')
    src=replace_once(src,'self.tabs.add(dashboard, text="개발 현황")',
                     'self.tabs.add(dashboard, text="AI 회사 운영센터")','first tab label')
    src=replace_once(src,'self.quick_navigation.set("개발 현황")',
                     'self.quick_navigation.set("AI 회사 운영센터")','navigation default')
    src=replace_once(src,'        self._dashboard(dashboard)\n',
                     '        from desktop.company_office_gui import mount as mount_company_office\n'
                     '        mount_company_office(self, dashboard)\n','office mount')
    src=replace_once(src,'        style.map("TNotebook.Tab", background=[("selected", "#3659ab")])',
                     '        style.map("TNotebook.Tab", background=[("selected", "#3659ab")])\n'
                     '        style.layout("AIWACK.TNotebook.Tab", [])','tab style')
    src=replace_once(src,'self.tabs = ttk.Notebook(outer)',
                     'self.tabs = ttk.Notebook(outer, style="AIWACK.TNotebook")','notebook')
    src=replace_once(src,'AI Autonomous Company  ·  Windows 데스크톱 초기 개발판',
                     'AI Autonomous Company  ·  AI 조직·업무·실제 모델 실행 현황','subtitle')
    src=replace_once(src,'실행 중인 웹 서버 없음  ·  사용자 PC의 로컬 SQLite 파일만 사용  ·  외부 전송 없음',
                     '실행 상태는 실제 SQLite·로컬 모델 기준  ·  대외 판매·결제는 별도 연동 검증 필요','footer')
    # Desktop 1040x720 first-launch window: reserve space for the actual company
    # action bar and status, instead of wasting 80px above the application.
    src=replace_once(src,'outer = tk.Frame(self.root, bg="#121c2d", padx=25, pady=20)',
                     'outer = tk.Frame(self.root, bg="#121c2d", padx=17, pady=11)',
                     'outer top whitespace')
    src=replace_once(src,'font=("Malgun Gothic", 26, "bold")',
                     'font=("Malgun Gothic", 22, "bold")','header size')
    src=replace_once(src,'pack(anchor="w", pady=(2, 15))',
                     'pack(anchor="w", pady=(1, 7))','header subtitle spacing')
    src=replace_once(src,'dashboard = tk.Frame(self.tabs, bg="#121c2d", padx=12, pady=16)',
                     'dashboard = tk.Frame(self.tabs, bg="#121c2d", padx=5, pady=6)',
                     'office viewport padding')
    src=replace_once(src,'font=("Malgun Gothic", 9)).pack(anchor="w", pady=(13, 0))',
                     'font=("Malgun Gothic", 9)).pack(anchor="w", pady=(5, 0))',
                     'footer spacing')
    ast.parse(src,filename=str(app_path))
    app_path.write_text(src,encoding='utf-8')
    store_path=project/'desktop/storage.py'
    src=store_path.read_text(encoding='utf-8')
    for start_name,end_name,marker in [
        ('    def begin_task_execution(', '    def finish_task_execution(', '직원 AI 실행'),
        ('    def begin_employee_model_call(', '    def finish_employee_model_call(', '직원 AI 호출')]:
        begin=src.index(start_name)
        end=src.index(end_name,begin)
        scope=src[begin:end]
        anchor='        with self._connect() as con:\n'
        if start_name.endswith('begin_task_execution('):
            anchor+='            con.execute("BEGIN IMMEDIATE")\n'
        guard=('            from desktop.stage87_90_management import stopped as emergency_stopped\n'
               '            if emergency_stopped(con):\n'
               f'                raise PermissionError("비상 정지 상태에서는 {marker}을 시작할 수 없습니다.")\n')
        scope=replace_once(scope,anchor,anchor+guard,marker+' stop guard')
        src=src[:begin]+scope+src[end:]
    ast.parse(src,filename=str(store_path))
    store_path.write_text(src,encoding='utf-8')
    print('AIWACK live office installed in extracted source ONLY:',project)

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: python validation/install_company_office.py PROJECT_ROOT')
    apply(Path(sys.argv[1]))
