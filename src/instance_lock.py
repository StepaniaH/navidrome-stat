"""Hold a process lock for the lifetime of one database-backed collector."""

import errno
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def database_instance_lock(database_path: str):
    """Refuse concurrent app instances before recovery or collection can run.

    The lock file stays in place so a waiting process cannot lock an unlinked
    inode. The operating system releases the advisory lock after a crash.
    """
    database = Path(database_path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    with database.with_name(database.name + ".lock").open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt

                if lock.tell() == 0:
                    lock.write(b"\0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise RuntimeError(
                "Another Navidrome Stat instance is using this database. "
                "Run one instance with one worker per database."
            ) from exc
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)
