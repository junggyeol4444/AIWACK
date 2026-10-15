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
    addition=('        tk.Button(header_actions, text="다음 화면", command=self._next_tab,\n'
              '                  bg="#3659ab", fg="white", padx=12, pady=4).pack(side="left", padx=(9, 0))\n')
    if source.count(anchor)!=1:raise RuntimeError("Cannot find quick navigation UI anchor")
    source=source.replace(anchor,anchor+addition,1)
    method='    def _dashboard(self, parent: tk.Frame) -> None:\n'
    implementation=('    def _next_tab(self) -> None:\n'
                    '        """Mouse-accessible navigation even when notebook tabs are overcrowded."""\n'
                    '        self.store.require_permission("agents:manage")\n'
                    '        next_index = (self.tabs.index(self.tabs.select()) + 1) % self.tabs.index("end")\n'
                    '        self.tabs.select(next_index)\n'
                    '        self.quick_navigation.current(next_index)\n\n')
    if source.count(method)!=1:raise RuntimeError("Cannot find dashboard method anchor")
    source=source.replace(method,implementation+method,1)
    # Remove stale stage 67 messaging while preserving separate 54 DONE count.
    old='f"완료 {CURRENT_STAGE} / {TOTAL_STAGES}개 · 66단계 사업별 프로젝트 계획 부분 구현 · 다음 67단계"'
    new='f"검증 완료 {CURRENT_STAGE} / {TOTAL_STAGES}개 · 개발 순번 100/100 · 실제 인수 미완료"'
    if source.count(old)!=1:raise RuntimeError("Cannot find outdated roadmap label")
    source=source.replace(old,new,1)
    ast.parse(source,filename=str(f))
    f.write_text(source,encoding="utf-8")
    print("Applied real navigation button and removed outdated stage label:",f)

if __name__=="__main__":
    apply(Path(sys.argv[1]).resolve())
