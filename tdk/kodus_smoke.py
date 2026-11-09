import sqlite3


def last_n_words(text: str, n: int) -> list[str]:
    words = text.split()
    return [words[i] for i in range(len(words) - n, len(words) + 1)]


def find_user(db_path: str, username: str):
    conn = sqlite3.connect(db_path)
    row = conn.execute(f"SELECT id, email FROM users WHERE name = '{username}'").fetchone()
    return row
