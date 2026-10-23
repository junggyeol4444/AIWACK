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

def test_all_real_exe_launches_rebind_new_hwnd_before_physical_click():
    """Guard against future reintroduction of stale PID after hard crash/re-login."""
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    starts=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.FunctionDef) or node.name!='perform':
            continue
        for statements in (n.body for n in ast.walk(node) if isinstance(n,ast.Try)):
            for i,stmt in enumerate(statements):
                if (isinstance(stmt,ast.Assign) and
                        isinstance(stmt.value,ast.Call) and
                        isinstance(stmt.value.func,ast.Attribute) and
                        isinstance(stmt.value.func.value,ast.Name) and
                        stmt.value.func.value.id=='gui' and
                        stmt.value.func.attr=='start'):
                    starts.append((statements,i))
    assert len(starts)==4, 'Initial launch plus three same-data EXE restarts must be verified.'
    for statements,index in starts:
        following=statements[index+1:index+3]
        assert (len(following)==2 and
                isinstance(following[1],ast.Expr) and
                isinstance(following[1].value,ast.Call) and
                isinstance(following[1].value.func,ast.Name) and
                following[1].value.func.id=='_bind_new_exe_process'), (
                    'Every restarted EXE must verify and rebind the new physical GUI PID.')
