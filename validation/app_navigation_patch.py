"""Validation-branch user-facing menu navigation improvement for the EXE candidate.
Never modifies the original archive on main; patches only extracted test workspace.
"""
from pathlib import Path
import ast
import sys

def apply(root: Path) -> None:
    f=root/"desktop"/"app.py"
    source=f.read_text(encoding="utf-8")
    anchor='        self.quick_navigation.bind("<<ComboboxSelected>>", self._jump_to_tab)\n'
    addition=('        tk.Button(header_actions, text="메모 실사", command=self._open_persistence,\n'
              '                  bg="#3659ab", fg="white", padx=12, pady=4).pack(side="left", padx=(9, 0))\n')
    if source.count(anchor)!=1:raise RuntimeError("Cannot find quick navigation UI anchor")
    source=source.replace(anchor,anchor+addition,1)
    method='    def _dashboard(self, parent: tk.Frame) -> None:\n'
    implementation=('    def _open_persistence(self, event=None) -> None:\n'
                    '        """One-click real GUI navigation to note persistence."""\n'
                    '        self.store.require_permission("notes:read")\n'
                    '        self.tabs.select(1)\n'
                    '        self.quick_navigation.current(1)\n'
                    '        self.root.after_idle(self.note_entry.focus_set)\n\n')
    if source.count(method)!=1:raise RuntimeError("Cannot find dashboard method anchor")
    source=source.replace(method,implementation+method,1)
    # Remove stale stage 67 messaging while preserving separate 54 DONE count.
    old='f"완료 {CURRENT_STAGE} / {TOTAL_STAGES}개 · 66단계 사업별 프로젝트 계획 부분 구현 · 다음 67단계"'
    new='f"검증 완료 {CURRENT_STAGE} / {TOTAL_STAGES}개 · 개발 순번 100/100 · 실제 인수 미완료"'
    if source.count(old)!=1:raise RuntimeError("Cannot find outdated roadmap label")
    source=source.replace(old,new,1)
    # Fix an actual EXE shutdown crash: after WM_DELETE_WINDOW destroys Tk,
    # calling winfo_exists() in the run() finally raises TclError and shows a
    # modal PyInstaller "Unhandled exception in script" dialog.
    old_shutdown='    finally:\n        if root.winfo_exists():\n            root.destroy()\n'
    safe_shutdown=('    finally:\n'
                   '        try:\n'
                   '            root.destroy()\n'
                   '        except tk.TclError:\n'
                   '            pass\n')
    if source.count(old_shutdown)!=1:
        raise RuntimeError("Cannot find exact EXE shutdown crash site")
    source=source.replace(old_shutdown,safe_shutdown,1)
    ast.parse(source,filename=str(f))
    f.write_text(source,encoding="utf-8")
    print("Applied real navigation button and removed outdated stage label:",f)

if __name__=="__main__":
    apply(Path(sys.argv[1]).resolve())
