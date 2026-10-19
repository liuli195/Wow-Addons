"""任务级预算、取消和进程所有权；只使用 Python 标准库。"""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid


_DIAGNOSTIC_LOCK = threading.Lock()
_DIAGNOSTIC_WALL_STAGES = (
    'diagnostic.total', 'native.execute', 'evaluation.report_read_validate', 'evaluation.trace',
    'candidate.compile', 'candidate.write', 'report.prepare', 'report.write', 'report.publish',
    'model.full_write', 'model.control_write', 'state.persist.full', 'state.persist.partial',
    'main.wait',
)


def diagnostic_start():
    """性能采集不能阻断业务；调用者只在总开关打开时进入。"""
    try:
        return time.perf_counter()
    except Exception:
        return None


def diagnostic_finish(owner, stage, started, **units):
    """只累加本次调用的含子阶段墙钟时间，不进入业务检查点。"""
    if started is None:
        return
    try:
        finished = time.perf_counter()
        seconds = max(0.0, finished - started)
        with _DIAGNOSTIC_LOCK:
            if not hasattr(owner, 'performance_stages'):
                owner.performance_stages = {}
            stats = owner.performance_stages.setdefault(stage, dict(calls=0, seconds=0.0, units={}))
            stats['calls'] += 1
            stats['seconds'] += seconds
            for name, count in units.items():
                stats['units'][name] = stats['units'].get(name, 0) + count
            # Only coarse stages retain intervals. Fine-grained rule entries stay aggregated.
            if stage in _DIAGNOSTIC_WALL_STAGES:
                if not hasattr(owner, 'performance_intervals'):
                    owner.performance_intervals = {}
                owner.performance_intervals.setdefault(stage, []).append((started, max(started, finished)))
    except Exception:
        # 计时或采集失败不能覆盖原业务返回值或原异常。
        pass


def diagnostic_candidate(owner, kind, identity, runtime):
    """本次新执行候选的观测里程碑；不写入或恢复业务检查点。"""
    try:
        elapsed = runtime.elapsed_seconds
        invocation = max(0.0, elapsed - runtime.used_seconds)
        with _DIAGNOSTIC_LOCK:
            if not hasattr(owner, 'performance_candidates'):
                owner.performance_candidates = {}
            owner.performance_candidates.setdefault(kind, {}).setdefault(identity, dict(
                behavior_identity=identity, invocation_seconds=invocation, budget_elapsed_seconds=elapsed))
    except Exception:
        pass


def diagnostic_summary(*owners):
    """独立于业务状态的本次调用汇总；嵌套和并发区间不能相加。"""
    stages, intervals = {}, {}
    candidates = {'first_score_published': {}, 'screening_archived': {}}
    with _DIAGNOSTIC_LOCK:
        for owner in owners:
            for name, value in getattr(owner, 'performance_stages', {}).items():
                stats = stages.setdefault(name, dict(calls=0, seconds=0.0, units={}))
                stats['calls'] += value['calls']
                stats['seconds'] += value['seconds']
                for unit, count in value['units'].items():
                    stats['units'][unit] = stats['units'].get(unit, 0) + count
            for name, spans in getattr(owner, 'performance_intervals', {}).items():
                intervals.setdefault(name, []).extend(spans)
            for kind, records in getattr(owner, 'performance_candidates', {}).items():
                for identity, record in records.items():
                    candidates[kind].setdefault(identity, record)
    def wall_union(spans):
        total, end = 0.0, None
        for start, stop in sorted(spans):
            total += stop - start if end is None or start > end else max(0.0, stop - end)
            end = stop if end is None else max(end, stop)
        return total
    for name, spans in intervals.items():
        stages[name]['wall_union_seconds'] = wall_union(spans)
    covered_stages = sorted(name for name in intervals if name != 'main.wait')
    return dict(scope='current_invocation', timing='inclusive_wall_seconds', stages=stages,
        covered_stages=covered_stages,
        covered_wall_seconds=wall_union(span for name in covered_stages for span in intervals[name]),
        covered_wall_timing=(
            'Union of selected coarse covered_stages, including I/O, lock and process waits; '
            'main.wait measures screen_round future.result only and is an overlapping wait indicator; it is excluded. '
            'This is not CPU time and not the complete public-call wall time.'),
        candidate_progress={kind: list(records.values()) for kind, records in candidates.items()},
        candidate_progress_timing=dict(
            invocation_seconds='Since this TaskRuntime.started; not the outer public-call start.',
            budget_elapsed_seconds='TaskRuntime elapsed including previously used budget.',
            first_score_published='New native search batch zero, validated and report-group transaction committed.',
            screening_archived='Newly executed candidate completed in-memory screening/archive flow; checkpoint may still be buffered.'))


def replace_file(source, destination):
    """Windows 读者可能短暂占用旧报告；有界重试，始终保留原子替换。"""
    for attempt in range(11):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 10:
                raise
            time.sleep(0.02)


class TaskCancelled(RuntimeError):
    """用户取消了当前任务。"""


class BudgetExceeded(RuntimeError):
    """任务或当前批次已用完预算。"""


class ProcessTimeout(RuntimeError):
    """单个原生进程超出允许时长。"""


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float


class TaskRuntime:
    """一次任务共享的截止时间和取消状态。"""

    def __init__(self, budget_seconds: float = 600.0, *, cancel_event=None, used_seconds: float = 0.0,
                 diagnostic_logging=False):
        if budget_seconds < 0 or used_seconds < 0 or used_seconds > budget_seconds:
            raise ValueError("任务预算必须满足 0 <= used <= total")
        if type(diagnostic_logging) is not bool:
            raise ValueError('诊断日志总开关必须为布尔值')
        self.diagnostic_logging = diagnostic_logging
        self.budget_seconds = float(budget_seconds)
        self.used_seconds = float(used_seconds)
        self.started = time.monotonic()
        self.cancel_event = cancel_event or threading.Event()
        self.identities = {}
        self.phase_limit = self.budget_seconds
        self.reservation = None

    @property
    def elapsed_seconds(self) -> float:
        return self.used_seconds + max(0.0, time.monotonic() - self.started)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, min(self.budget_seconds, self.phase_limit) - self.elapsed_seconds)

    def check(self) -> None:
        if self.cancel_event.is_set():
            raise TaskCancelled("任务已取消")
        if self.remaining_seconds <= 0:
            raise BudgetExceeded("任务已达到十分钟计算上限")

    def limit(self, requested: float | None = None) -> float:
        self.check()
        available = self.remaining_seconds
        return min(available, requested) if requested is not None else available

    def cancel(self) -> None:
        # 句柄只由各自运行线程操作，取消线程不触碰可能已经关闭的句柄。
        self.cancel_event.set()


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _HANDLE = wintypes.HANDLE
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _INFINITE = 0xFFFFFFFF
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 258
    _STILL_ACTIVE = 259
    _CREATE_UNICODE_ENVIRONMENT = 0x00000400
    _CREATE_NEW_PROCESS_GROUP = 0x00000200
    _EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    _STARTF_USESTDHANDLES = 0x00000100
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _FILE_SHARE_READ = 0x00000001
    _FILE_SHARE_WRITE = 0x00000002
    _CREATE_ALWAYS = 2
    _OPEN_EXISTING = 3
    _FILE_ATTRIBUTE_NORMAL = 0x00000080
    _STD_INPUT_HANDLE = -10
    _PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
    _PROC_THREAD_ATTRIBUTE_JOB_LIST = 0x0002000D
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    class _SECURITY_ATTRIBUTES(ctypes.Structure):
        _fields_ = [
            ("nLength", wintypes.DWORD),
            ("lpSecurityDescriptor", wintypes.LPVOID),
            ("bInheritHandle", wintypes.BOOL),
        ]

    class _STARTUPINFO(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", wintypes.LPBYTE),
            ("hStdInput", _HANDLE),
            ("hStdOutput", _HANDLE),
            ("hStdError", _HANDLE),
        ]

    class _STARTUPINFOEX(ctypes.Structure):
        _fields_ = [("StartupInfo", _STARTUPINFO), ("lpAttributeList", wintypes.LPVOID)]

    class _PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("hProcess", _HANDLE),
            ("hThread", _HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", wintypes.ULARGE_INTEGER),
            ("WriteOperationCount", wintypes.ULARGE_INTEGER),
            ("OtherOperationCount", wintypes.ULARGE_INTEGER),
            ("ReadTransferCount", wintypes.ULARGE_INTEGER),
            ("WriteTransferCount", wintypes.ULARGE_INTEGER),
            ("OtherTransferCount", wintypes.ULARGE_INTEGER),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class _JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", wintypes.LARGE_INTEGER),
            ("TotalKernelTime", wintypes.LARGE_INTEGER),
            ("ThisPeriodTotalUserTime", wintypes.LARGE_INTEGER),
            ("ThisPeriodTotalKernelTime", wintypes.LARGE_INTEGER),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    _kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = _HANDLE
    _kernel32.SetInformationJobObject.argtypes = [_HANDLE, wintypes.INT, wintypes.LPVOID, wintypes.DWORD]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.InitializeProcThreadAttributeList.argtypes = [wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t)]
    _kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    _kernel32.UpdateProcThreadAttribute.argtypes = [wintypes.LPVOID, wintypes.DWORD, ctypes.c_size_t, wintypes.LPVOID, ctypes.c_size_t, wintypes.LPVOID, ctypes.POINTER(ctypes.c_size_t)]
    _kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    _kernel32.DeleteProcThreadAttributeList.argtypes = [wintypes.LPVOID]
    _kernel32.DeleteProcThreadAttributeList.restype = None
    _kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(_SECURITY_ATTRIBUTES),
        ctypes.POINTER(_SECURITY_ATTRIBUTES), wintypes.BOOL, wintypes.DWORD,
        wintypes.LPVOID, wintypes.LPCWSTR, ctypes.POINTER(_STARTUPINFO),
        ctypes.POINTER(_PROCESS_INFORMATION),
    ]
    _kernel32.CreateProcessW.restype = wintypes.BOOL
    _kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.POINTER(_SECURITY_ATTRIBUTES), wintypes.DWORD,
                                      wintypes.DWORD, _HANDLE]
    _kernel32.CreateFileW.restype = _HANDLE
    _kernel32.CloseHandle.argtypes = [_HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = [_HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetExitCodeProcess.argtypes = [_HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [_HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.QueryInformationJobObject.argtypes = [_HANDLE, wintypes.INT, wintypes.LPVOID,
                                                    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _kernel32.QueryInformationJobObject.restype = wintypes.BOOL


class _OwnedProcess:
    def __init__(self, process_handle, job_handle, stdout_path, stderr_path):
        self._process_handle = process_handle
        self._job_handle = job_handle
        self.stdout_path = stdout_path
        self.stderr_path = stderr_path
        self._closed = False

    def poll(self):
        code = wintypes.DWORD()
        if not _kernel32.GetExitCodeProcess(self._process_handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return None if code.value == _STILL_ACTIVE else code.value

    def terminate(self):
        if self._active_processes() and not _kernel32.TerminateJobObject(self._job_handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def _active_processes(self):
        info = _JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        size = wintypes.DWORD()
        if not _kernel32.QueryInformationJobObject(
            self._job_handle, 1, ctypes.byref(info), ctypes.sizeof(info), ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return info.ActiveProcesses

    def wait(self, timeout_seconds):
        milliseconds = max(0, int(timeout_seconds * 1000))
        started = time.monotonic()
        while True:
            result = _kernel32.WaitForSingleObject(self._process_handle, min(50, milliseconds))
            if result not in (_WAIT_OBJECT_0, _WAIT_TIMEOUT):
                raise ctypes.WinError(ctypes.get_last_error())
            if result == _WAIT_OBJECT_0 and self._active_processes() == 0:
                return self.poll()
            if time.monotonic() - started >= timeout_seconds:
                raise ProcessTimeout("原生进程超时")

    def close(self):
        if self._closed:
            return
        self._closed = True
        if os.name == "nt":
            _kernel32.CloseHandle(self._process_handle)
            _kernel32.CloseHandle(self._job_handle)
        else:
            self._process_handle = None


def _open_redirect(path: Path, access: int, disposition: int):
    security = _SECURITY_ATTRIBUTES(ctypes.sizeof(_SECURITY_ATTRIBUTES), None, True)
    handle = _kernel32.CreateFileW(str(path), access, _FILE_SHARE_READ | _FILE_SHARE_WRITE,
                                   ctypes.byref(security), disposition, _FILE_ATTRIBUTE_NORMAL, None)
    if handle in (None, _INVALID_HANDLE_VALUE):
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def _create_windows_process(command, cwd: Path, folder: Path):
    job = _kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    stdout_path = folder / (".stdout-" + uuid.uuid4().hex + ".tmp")
    stderr_path = folder / (".stderr-" + uuid.uuid4().hex + ".tmp")
    stdin_handle = stdout_handle = stderr_handle = None
    attribute_list = None
    created = False
    info = _PROCESS_INFORMATION()
    try:
        limits = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                                  ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        stdin_handle = _open_redirect("NUL", _GENERIC_READ, _OPEN_EXISTING)
        stdout_handle = _open_redirect(stdout_path, _GENERIC_WRITE, _CREATE_ALWAYS)
        stderr_handle = _open_redirect(stderr_path, _GENERIC_WRITE, _CREATE_ALWAYS)
        size = ctypes.c_size_t()
        _kernel32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
        attribute_list = (ctypes.c_byte * size.value)()
        if not _kernel32.InitializeProcThreadAttributeList(ctypes.byref(attribute_list), 2, 0, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        job_handles = (_HANDLE * 1)(job)
        child_handles = (_HANDLE * 3)(stdin_handle, stdout_handle, stderr_handle)
        if not _kernel32.UpdateProcThreadAttribute(
            ctypes.byref(attribute_list), 0, _PROC_THREAD_ATTRIBUTE_JOB_LIST,
            ctypes.cast(job_handles, wintypes.LPVOID), ctypes.sizeof(job_handles), None, None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        if not _kernel32.UpdateProcThreadAttribute(
            ctypes.byref(attribute_list), 0, _PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            ctypes.cast(child_handles, wintypes.LPVOID), ctypes.sizeof(child_handles), None, None
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        startup = _STARTUPINFOEX()
        startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEX)
        startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = stdin_handle
        startup.StartupInfo.hStdOutput = stdout_handle
        startup.StartupInfo.hStdError = stderr_handle
        startup.lpAttributeList = ctypes.cast(attribute_list, wintypes.LPVOID)
        info = _PROCESS_INFORMATION()
        command_line = ctypes.create_unicode_buffer(subprocess.list2cmdline([str(part) for part in command]))
        if not _kernel32.CreateProcessW(
            str(Path(command[0]).resolve()), command_line, None, None, True,
            _EXTENDED_STARTUPINFO_PRESENT | _CREATE_UNICODE_ENVIRONMENT, None,
            str(cwd.resolve()), ctypes.byref(startup.StartupInfo), ctypes.byref(info)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        _kernel32.CloseHandle(info.hThread)
        info.hThread=None
        owned = _OwnedProcess(info.hProcess, job, stdout_path, stderr_path)
        created = True
        return owned
    except BaseException:
        if info.hProcess:
            owned=_OwnedProcess(info.hProcess,job,stdout_path,stderr_path)
            owned.terminate()
            while True:
                try:
                    owned.wait(0.1)
                    break
                except ProcessTimeout:
                    continue
            owned.close()
        else:
            _kernel32.CloseHandle(job)
        if info.hThread:
            _kernel32.CloseHandle(info.hThread)
        raise
    finally:
        if attribute_list is not None:
            _kernel32.DeleteProcThreadAttributeList(ctypes.byref(attribute_list))
        for handle in (stdin_handle, stdout_handle, stderr_handle):
            if handle:
                _kernel32.CloseHandle(handle)
        if not created:
            stdout_path.unlink(missing_ok=True)
            stderr_path.unlink(missing_ok=True)


def _create_process(command, cwd: Path, folder: Path):
    if os.name != "nt":
        raise OSError("Sim2GSE 任务进程仅支持 Windows Job Object")
    return _create_windows_process(command, cwd, folder)


def run_command(command, cwd, *, timeout_seconds: float, runtime: TaskRuntime | None = None,
                output_dir=None, on_start=None):
    """以 Job Object（作业对象）原子绑定方式运行一个外部命令。"""

    runtime = runtime or TaskRuntime(timeout_seconds)
    allowed = runtime.limit(timeout_seconds)
    folder = Path(output_dir or cwd)
    folder.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    runtime.check()
    reservation = uuid.uuid4().hex
    if runtime.reservation:
        runtime.reservation(reservation, allowed)
    process = None
    try:
        process = _create_process(command, Path(cwd), folder)
    except BaseException:
        if runtime.reservation:
            runtime.reservation(reservation, None)
        raise
    try:
        if on_start is not None:
            on_start()
        while True:
            if runtime.cancel_event.is_set():
                process.terminate()
                try:
                    process.wait(2.0)
                except ProcessTimeout as error:
                    raise TaskCancelled("任务已取消，进程仍在收尾") from error
                raise TaskCancelled("任务已取消")
            elapsed = time.monotonic() - started
            if elapsed >= allowed or runtime.remaining_seconds <= 0:
                process.terminate()
                try:
                    process.wait(2.0)
                except ProcessTimeout:
                    pass
                raise BudgetExceeded("原生进程耗尽任务预算") if runtime.remaining_seconds <= 0 else ProcessTimeout("原生进程超时")
            code = process.poll()
            if code is not None:
                break
            # 程序退出时立即唤醒；最长仍每50毫秒检查取消与共享预算。
            try:
                process.wait(min(0.05, allowed - elapsed, runtime.remaining_seconds))
            except ProcessTimeout:
                pass
        stdout = process.stdout_path.read_bytes() if process.stdout_path.exists() else b""
        stderr = process.stderr_path.read_bytes() if process.stderr_path.exists() else b""
        return ProcessResult(code, stdout, stderr, time.monotonic() - started)
    finally:
        # 完整等待作业成员退出；两秒是收尾目标，不是假称成功的截止点。
        process.terminate()
        while True:
            try:
                process.wait(0.1)
                break
            except ProcessTimeout:
                continue
        process.close()
        if runtime.reservation:
            runtime.reservation(reservation, None)
        for path in (process.stdout_path, process.stderr_path):
            for attempt in range(11):
                try:
                    path.unlink(missing_ok=True)
                    break
                except PermissionError as error:
                    if getattr(error, "winerror", None) != 32 or attempt == 10:
                        raise
                    time.sleep(0.02)


__all__ = ["BudgetExceeded", "ProcessResult", "ProcessTimeout", "TaskCancelled", "TaskRuntime", "run_command"]
