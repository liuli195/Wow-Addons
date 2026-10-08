"""Coordinate foreground searches with manual seed training through the shared center."""

from __future__ import annotations

from contextlib import contextmanager
import msvcrt
from pathlib import Path
import threading
import time
import uuid


class ActivityConflict(RuntimeError):
    """Another incompatible seed activity is active."""


def _activity_directory():
    from result_store import DATA_ROOT

    root = Path(DATA_ROOT)
    if not root.is_dir():
        raise ActivityConflict('既有数据中心不可用，无法协调搜索与起点整理')
    directory = root / '.seed-activity'
    directory.mkdir(exist_ok=True)
    return directory


def _open_lock(path):
    handle = path.open('a+b')
    handle.seek(0, 2)
    if handle.tell() == 0:
        handle.write(b'0')
        handle.flush()
    handle.seek(0)
    return handle


def _try_lock(path):
    try:
        handle = _open_lock(path)
    except FileNotFoundError:
        return False
    try:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return True
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return False
    finally:
        handle.close()


def _normal_search_active(directory):
    for marker in directory.glob('normal-*.lock'):
        if _try_lock(marker):
            return True
    return False


@contextmanager
def foreground_search():
    """Register one foreground search without waiting for a training run."""
    directory = _activity_directory()
    marker = directory / f'normal-{uuid.uuid4().hex}.lock'
    handle = _open_lock(marker)
    locked = False
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        locked = True
        yield
    finally:
        try:
            if locked:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()
            try:
                marker.unlink(missing_ok=True)
            except PermissionError:
                # A concurrent training probe may have it open; unlocked leftovers
                # are safe because probes test the lock, not filename existence.
                pass


@contextmanager
def training_activity(*, poll_seconds=0.05):
    """Reject an already-running search and stop this training when one starts."""
    directory = _activity_directory()
    stopped = threading.Event()
    cancel = threading.Event()
    handle = _open_lock(directory / 'training.lock')
    locked = False
    try:
        if _normal_search_active(directory):
            raise ActivityConflict('正常搜索正在运行，起点整理已停止')
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            locked = True
        except OSError as error:
            raise ActivityConflict('另一起点整理正在执行') from error

        def watch_searches():
            while not stopped.wait(poll_seconds):
                try:
                    active = _normal_search_active(directory)
                except OSError:
                    active = True
                if active:
                    cancel.set()
                    return

        watcher = threading.Thread(target=watch_searches, name='seed-training-watch', daemon=True)
        watcher.start()
        try:
            yield cancel
        finally:
            stopped.set()
            watcher.join(max(0.1, poll_seconds * 3))
    finally:
        # Only this process's own training lock is released.
        try:
            if locked:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        handle.close()


__all__ = ['ActivityConflict', 'foreground_search', 'training_activity']
