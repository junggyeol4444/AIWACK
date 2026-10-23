"""Physical-window owner PID contract; Linux simulation is NOT Windows proof."""
import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

SOURCE=Path(__file__).with_name('windows_packaged_real_gguf_queue_e2e.py')

def bind(root=55, owner=77, descendants=(55,77), title='AIWACK'):
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    defs=[n for n in tree.body if isinstance(n,ast.FunctionDef)
          and n.name=='_bind_new_exe_process']
    assert len(defs)==1
    env={'_TARGET_EXE_PID':None,'_WINDOW_IDENTITY':{41:('stale',9)},
         'WINDOW_TITLES':{41:'stale'},'WINDOW_PIDS':{'stale':9},
         'gui':SimpleNamespace(TITLE='AIWACK'), '_is_window':lambda hwnd:True,
         '_native_window_pid':lambda hwnd:owner,
         '_windows_process_tree':lambda pid:set(descendants)}
    code=compile(ast.fix_missing_locations(ast.Module(body=defs,type_ignores=[])),
                 str(SOURCE),'exec')
    exec(code,env)
    return env,SimpleNamespace(pid=root,poll=lambda:None),SimpleNamespace(_hWnd=57,title=title)

def test_pyinstaller_child_pid_bound_without_using_bootstrap_as_window_owner():
    env,process,window=bind()
    assert env['_bind_new_exe_process'](process,window)==77
    assert env['_TARGET_EXE_PID']==77
    assert env['WINDOW_PIDS']=={'AIWACK':77}
    assert env['_WINDOW_IDENTITY']=={57:('AIWACK',77)}

@pytest.mark.parametrize('owner,descendants,title',[
    (88,(55,77),'AIWACK'),(77,(55,77),'Another Window'),(0,(55,77),'AIWACK')])
def test_foreign_or_wrong_title_window_cannot_be_bound(owner,descendants,title):
    env,process,window=bind(owner=owner,descendants=descendants,title=title)
    with pytest.raises(AssertionError):env['_bind_new_exe_process'](process,window)
    assert env['_TARGET_EXE_PID'] is None
    assert env['WINDOW_PIDS']=={'stale':9}

@pytest.mark.parametrize('pid,exit_code',[(0,None),(55,1)])
def test_dead_or_invalid_bootstrap_never_binds(pid,exit_code):
    env,process,window=bind(root=pid)
    process.poll=lambda:exit_code
    with pytest.raises(AssertionError):env['_bind_new_exe_process'](process,window)
