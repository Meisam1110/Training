import sqlite3,sys
c=sqlite3.connect(sys.argv[1] if len(sys.argv)>1 else '/tmp/qa/main.db');c.execute('delete from login_attempts');c.commit()
