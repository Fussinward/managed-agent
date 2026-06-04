import sqlite3

class Session:
    def __init__(self, session_id: int):
        self.conn = sqlite3.connect("sessions.db")
        self.c = self.conn.cursor()
        self.session_id = session_id
        res = self.c.execute('''SELECT MAX(ROW_INDEX) FROM SESSIONS WHERE
                                      SESSION_ID = ?''', (self.session_id,))
        row = res.fetchone()                                      
        self.row_index = (row[0] + 1) if row[0] is not None else 0
        pass

    @staticmethod
    def get_container_id(session_id: int) -> str|None:
        '''get container id from current session id'''
        conn = sqlite3.connect("sessions.db")
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS SBX_SESSIONS(
                  SESSION_ID INT PRIMARY KEY,
                  CONTAINER_ID TEXT NOT NULL)
                  ''')
        res = c.execute('''SELECT CONTAINER_ID FROM SBX_SESSIONS WHERE SESSION_ID = ?''', (session_id, ))
        row = res.fetchone()
        return row[0] if row else None

    @staticmethod
    def change_container_id(session_id: int, new_container_id: str) -> None:
        '''change container id for current session'''
        conn = sqlite3.connect("sessions.db")
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO SBX_SESSIONS (SESSION_ID, CONTAINER_ID)
                     VALUES (?, ?)''', (session_id, new_container_id))
        conn.commit()
        pass

    @staticmethod
    def select_session_id() -> int:
        conn = sqlite3.connect("sessions.db")
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS
                    SESSIONS
                (ROW_INDEX    INT   NOT NULL,
                SESSION_ID   INT   NOT NULL,
                ROLE         TEXT  NOT NULL,
                CONTENT      TEXT  NOT NULL,
                PRIMARY KEY (SESSION_ID, ROW_INDEX));
                ''')
        res = c.execute('''SELECT DISTINCT SESSION_ID FROM SESSIONS''')
        row = res.fetchall()
        ids = []
        for item in row:
            ids.append(item[0])

        if not ids:
            return 0
        print(f"current session ids: {ids}")
        id = int(input("type the number to select or type -1 to create a new session: "))
        if id == -1:
            return max(ids) + 1
        elif id not in ids:
            print("invalid id")
            raise ValueError
        return id

    def emit_event(self, message: dict) -> None:
        self.c.execute('''INSERT INTO SESSIONS (SESSION_ID, ROW_INDEX, ROLE, CONTENT)
                    VALUES (?, ?, ?, ?)''',
                (self.session_id, self.row_index, message["role"], message["content"])) 
        self.row_index += 1
        self.conn.commit()

    def get_session(self) -> list[dict]:
        res = self.c.execute('''SELECT ROLE, CONTENT FROM SESSIONS WHERE SESSION_ID = ?
                           ORDER BY ROW_INDEX''', (self.session_id, ))
        rows = res.fetchall()
        hist = []
        for role, content in rows:
            hist.append({"role": role, "content": content})
        print("get session, len: ", len(hist))
        return hist
    
    def get_recent_session(self) -> list[dict]:
        '''get the latest 5 dialogues or the uncompressed dialogues'''