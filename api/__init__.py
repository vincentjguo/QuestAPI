import sqlite3

from api.database.db import database

with sqlite3.connect(database) as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS users (token TEXT PRIMARY KEY, cookies TEXT, user TEXT)")


