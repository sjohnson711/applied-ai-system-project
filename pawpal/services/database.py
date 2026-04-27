import sqlite3
from datetime import datetime
from typing import Optional
from pawpal.models import Owner, Pet, Task

_DB = "pawpal.db"


def init_db() -> None:
    """Create all tables if they don't exist, then run any pending migrations."""
    con = sqlite3.connect(_DB)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            email         TEXT PRIMARY KEY,
            name          TEXT NOT NULL,
            password_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS owner_prefs (
            email               TEXT PRIMARY KEY REFERENCES users(email),
            max_tasks_per_day   INTEGER NOT NULL DEFAULT 5,
            available_minutes   INTEGER NOT NULL DEFAULT 90
        );
        CREATE TABLE IF NOT EXISTS pets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_email TEXT    NOT NULL REFERENCES users(email),
            name        TEXT    NOT NULL,
            species     TEXT    NOT NULL,
            breed       TEXT    NOT NULL DEFAULT '',
            age         INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            pet_id      INTEGER NOT NULL REFERENCES pets(id),
            description TEXT    NOT NULL,
            time        TEXT,
            frequency   TEXT    NOT NULL DEFAULT '',
            completed   INTEGER NOT NULL DEFAULT 0,
            duration    INTEGER NOT NULL DEFAULT 0,
            priority    TEXT    NOT NULL DEFAULT 'medium'
        );
    """)

    # Migration: add username column if it does not already exist
    cols = [row[1] for row in con.execute("PRAGMA table_info(users)").fetchall()]
    if "username" not in cols:
        con.execute("ALTER TABLE users ADD COLUMN username TEXT DEFAULT ''")
        # Backfill existing rows using the email prefix (part before @), lowercased
        con.execute("""
            UPDATE users
            SET username = LOWER(SUBSTR(email, 1, INSTR(email, '@') - 1))
            WHERE username = ''
        """)
        con.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )

    con.commit()
    con.close()


def create_user(email: str, username: str, name: str, password_hash: str) -> bool:
    """Insert a new user; returns False if the email or username already exists."""
    try:
        con = sqlite3.connect(_DB)
        con.execute(
            "INSERT INTO users (email, username, name, password_hash) VALUES (?, ?, ?, ?)",
            (email, username, name, password_hash),
        )
        con.execute("INSERT OR IGNORE INTO owner_prefs (email) VALUES (?)", (email,))
        con.commit()
        con.close()
        return True
    except sqlite3.IntegrityError:
        con.close()
        return False


def get_user(email: str) -> Optional[dict]:
    """Return the user row as a dict keyed by email, or None if not found."""
    return get_user_by_email(email)


def get_user_by_email(email: str) -> Optional[dict]:
    """Look up a user by email address. Returns a dict or None."""
    con = sqlite3.connect(_DB)
    row = con.execute(
        "SELECT email, username, name, password_hash FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    con.close()
    if row:
        return {"email": row[0], "username": row[1], "name": row[2], "password_hash": row[3]}
    return None


def get_user_by_username(username: str) -> Optional[dict]:
    """Look up a user by username (case-insensitive). Returns a dict or None."""
    con = sqlite3.connect(_DB)
    row = con.execute(
        "SELECT email, username, name, password_hash FROM users WHERE username = ?",
        (username.strip().lower(),),
    ).fetchone()
    con.close()
    if row:
        return {"email": row[0], "username": row[1], "name": row[2], "password_hash": row[3]}
    return None


def update_password(email: str, new_hash: str) -> bool:
    """Replace the stored password hash for the given email. Returns True if a row was updated."""
    con = sqlite3.connect(_DB)
    cur = con.execute(
        "UPDATE users SET password_hash = ? WHERE email = ?",
        (new_hash, email),
    )
    con.commit()
    updated = cur.rowcount > 0
    con.close()
    return updated


def save_owner(owner: Owner, email: str) -> None:
    """Upsert owner preferences, pets, and tasks for the given user email."""
    try:
        con = sqlite3.connect(_DB)
        prefs = owner.preferences
        con.execute(
            """INSERT INTO owner_prefs (email, max_tasks_per_day, available_minutes)
               VALUES (?, ?, ?)
               ON CONFLICT(email) DO UPDATE SET
                   max_tasks_per_day = excluded.max_tasks_per_day,
                   available_minutes = excluded.available_minutes""",
            (email, prefs.get("max_tasks_per_day", 5), prefs.get("available_minutes", 90)),
        )

        for pet in owner.pets:
            if getattr(pet, "_db_id", None):
                con.execute(
                    "UPDATE pets SET name=?, species=?, breed=?, age=? WHERE id=?",
                    (pet.name, pet.species, pet.breed, pet.age, pet._db_id),
                )
            else:
                cur = con.execute(
                    "INSERT INTO pets (owner_email, name, species, breed, age) VALUES (?, ?, ?, ?, ?)",
                    (email, pet.name, pet.species, pet.breed, pet.age),
                )
                pet._db_id = cur.lastrowid

            for task in pet.get_tasks():
                time_str = task.time.isoformat() if task.time else None
                if getattr(task, "_db_id", None):
                    con.execute(
                        """UPDATE tasks
                           SET description=?, time=?, frequency=?, completed=?,
                               duration=?, priority=?
                           WHERE id=?""",
                        (
                            task.description, time_str, task.frequency,
                            int(task.completed), task.duration, task.priority,
                            task._db_id,
                        ),
                    )
                else:
                    cur = con.execute(
                        """INSERT INTO tasks
                           (pet_id, description, time, frequency, completed, duration, priority)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            pet._db_id, task.description, time_str,
                            task.frequency, int(task.completed),
                            task.duration, task.priority,
                        ),
                    )
                    task._db_id = cur.lastrowid

        con.commit()
        con.close()
    except sqlite3.Error as e:
        raise RuntimeError(f"Failed to save data: {e}") from e


def delete_task(task_db_id: int) -> None:
    """Delete a single task row by its primary key."""
    con = sqlite3.connect(_DB)
    con.execute("DELETE FROM tasks WHERE id = ?", (task_db_id,))
    con.commit()
    con.close()


def load_owner(email: str) -> Optional[Owner]:
    """Reconstruct the full Owner / Pet / Task graph from the database."""
    try:
        con = sqlite3.connect(_DB)
        user_row = con.execute(
            "SELECT name FROM users WHERE email = ?", (email,)
        ).fetchone()
        if not user_row:
            con.close()
            return None

        pref_row = con.execute(
            "SELECT max_tasks_per_day, available_minutes FROM owner_prefs WHERE email = ?",
            (email,),
        ).fetchone()

        owner = Owner(
            name=user_row[0],
            preferences={
                "max_tasks_per_day": pref_row[0] if pref_row else 5,
                "available_minutes": pref_row[1] if pref_row else 90,
            },
        )

        for pet_row in con.execute(
            "SELECT id, name, species, breed, age FROM pets WHERE owner_email = ?", (email,)
        ).fetchall():
            pet = Pet(name=pet_row[1], species=pet_row[2], breed=pet_row[3], age=pet_row[4])
            pet._db_id = pet_row[0]

            for task_row in con.execute(
                """SELECT id, description, time, frequency, completed, duration, priority
                   FROM tasks WHERE pet_id = ?""",
                (pet_row[0],),
            ).fetchall():
                try:
                    time_val = datetime.fromisoformat(task_row[2]) if task_row[2] else None
                except (ValueError, TypeError):
                    time_val = None
                task = Task(
                    description=task_row[1],
                    time=time_val,
                    frequency=task_row[3],
                    completed=bool(task_row[4]),
                    duration=task_row[5],
                    priority=task_row[6],
                )
                task._db_id = task_row[0]
                pet.add_task(task)

            owner.add_pet(pet)

        con.close()
        return owner
    except sqlite3.Error:
        return None
