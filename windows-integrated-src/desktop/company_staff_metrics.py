"""Read-only actual employee activity metrics, never model-estimated revenue."""
from __future__ import annotations


def snapshot(store) -> dict:
    store.require_permission('company:manage')
    with store._connect() as con:
        # 실제 모델 실행과 결과물 승인 수치를 별도로 집계하여 JOIN에 의한 중복 계산 방지.
        employee_rows=con.execute("""SELECT e.id,e.display_name,
          COALESCE(d.name,'미배정') AS department,
          COALESCE(r.total_runs,0),COALESCE(r.success,0),
          COALESCE(r.fail,0),COALESCE(r.cancel,0),COALESCE(r.running,0),
          COALESCE(a.approved,0), COALESCE(m.calls,0), COALESCE(m.ok,0)
          FROM ai_employee_profiles e
          LEFT JOIN company_departments d ON d.id=e.department_id
          LEFT JOIN (
              SELECT employee_id,COUNT(*) AS total_runs,
                SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status IN ('failure','timeout','interrupted') THEN 1 ELSE 0 END) AS fail,
                SUM(CASE WHEN status='cancelled' THEN 1 ELSE 0 END) AS cancel,
                SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) AS running
              FROM company_task_runs GROUP BY employee_id
          ) r ON r.employee_id=e.id
          LEFT JOIN (
              SELECT r.employee_id,COUNT(*) AS approved
              FROM company_task_artifacts a
              JOIN company_task_runs r ON r.id=a.run_id
              WHERE a.review_status='approved'
              GROUP BY r.employee_id
          ) a ON a.employee_id=e.id
          LEFT JOIN (
              SELECT employee_id, COUNT(*) AS calls,
                 SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS ok
              FROM ai_model_call_history GROUP BY employee_id
          ) m ON m.employee_id=e.id
          ORDER BY e.id""").fetchall()
        statuses={row[0]:row[1] for row in con.execute(
            "SELECT status,COUNT(*) FROM company_tasks GROUP BY status")}
        actual=con.execute("SELECT COUNT(*) FROM ai_model_call_history WHERE status='success'").fetchone()[0]
        pending=con.execute("SELECT COUNT(*) FROM company_task_artifacts WHERE review_status='pending'").fetchone()[0]
    employees=[]
    for rid,name,dept,total,success,fail,cancel,running,approved,model_attempts,model_ok in employee_rows:
        # Cancelled attempts are neither success nor failed completed inference.
        completed=success+fail
        employees.append(dict(employee_id=int(rid),name=str(name),
             department=str(dept),actual_attempts=int(total),
             successful=int(success),failed=int(fail),cancelled=int(cancel),
             running=int(running),owner_approved_artifacts=int(approved),
             audited_model_calls=int(model_attempts), successful_model_calls=int(model_ok),
             observed_success_rate=None if completed==0 else round(success*100/completed,1)))
    return {'staff':employees,'employees':len(employees),
            'task_states':statuses,'pending_reviews':int(pending),
            'recorded_successful_model_calls':int(actual),
            'distinct_employees_with_successful_model_calls':sum(
                bool(e['successful_model_calls']) for e in employees),
            'all_31_model_calls_observed_in_sqlite':(
                len(employees)>=31 and sum(bool(e['successful_model_calls'])
                for e in employees)>=31),
            'financial_revenue_verified':False,
            'performance_is_only_observed_execution_counts':True,
            'external_business_outcomes_verified':False}


def text_report(store, max_employees: int=31) -> str:
    if type(max_employees) is not int or not 1<=max_employees<=100:
        raise ValueError('직원 분석 수는 1~100명이어야 합니다.')
    data=snapshot(store)
    lines=[f"실제 등록 직원: {data['employees']}명",
           f"실제 로컬 모델 성공 호출 기록: {data['recorded_successful_model_calls']}회",
           f"서로 다른 직원의 성공 모델 호출 감사: {data['distinct_employees_with_successful_model_calls']}명 / 31명 목표",
           '모델 호출 감사와 실제 GGUF 확인은 별도입니다. 업무 결과 승인·협업 완료로 계산하지 않습니다.',
           f"실제 결과 검수 대기: {data['pending_reviews']}건",
           "업무 상태: "+', '.join(f'{k} {v}건' for k,v in sorted(data['task_states'].items())),
           "직원별 실제 실행(성공/실패/취소/실행중/승인된 결과물):"]
    for worker in data['staff'][:max_employees]:
        lines.append(f"#{worker['employee_id']} {worker['name']} ({worker['department']}): "
              f"{worker['successful']}/{worker['failed']}/{worker['cancelled']}/"
              f"{worker['running']}/{worker['owner_approved_artifacts']}"
              f" · 관찰된 완료 실행 성공률 "
              f"{worker['observed_success_rate'] if worker['observed_success_rate'] is not None else '기록 없음'}"
              f" · 모델 호출 감사 {worker['successful_model_calls']}/{worker['audited_model_calls']}")
    lines.append('주의: 모델 성공 호출 횟수는 결과 내용의 품질·실제 판매·매출을 의미하지 않습니다.')
    return '\n'.join(lines)
