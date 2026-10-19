"""Stage41 offline, owner-mediated employee-to-employee message records."""

def initialize(con):
    con.execute("""CREATE TABLE IF NOT EXISTS employee_direct_messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      sender_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
      recipient_id INTEGER NOT NULL REFERENCES ai_employee_profiles(id) ON DELETE RESTRICT,
      subject TEXT NOT NULL, body TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      read_at TEXT,
      CHECK(sender_id <> recipient_id))""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_direct_messages_recipient ON employee_direct_messages(recipient_id,id DESC)")


def send(con, sender_id, recipient_id, subject, body):
    if any(type(v) is not int or v < 1 for v in (sender_id, recipient_id)) or sender_id == recipient_id:
        raise ValueError('서로 다른 유효한 직원 ID가 필요합니다.')
    if not isinstance(subject,str) or not 1 <= len(subject.strip()) <= 120:
        raise ValueError('제목은 1~120자여야 합니다.')
    if not isinstance(body,str) or not 1 <= len(body.strip()) <= 4000:
        raise ValueError('본문은 1~4000자여야 합니다.')
    rows=con.execute('SELECT id,lifecycle FROM ai_employee_profiles WHERE id IN (?,?)',(sender_id,recipient_id)).fetchall()
    if len(rows)!=2 or any(status!='draft' for _,status in rows):
        raise ValueError('발신자와 수신자는 등록된 비활성화되지 않은 직원이어야 합니다.')
    return con.execute('INSERT INTO employee_direct_messages(sender_id,recipient_id,subject,body) VALUES(?,?,?,?)',
                       (sender_id,recipient_id,subject.strip(),body.strip())).lastrowid
