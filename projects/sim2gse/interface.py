"""Sim2GSE（角色级按键序列优化器）的本地三步界面服务。"""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
import uuid

from task import TaskError, cancel_task, parse_character, read_task, start_task


PAGE = (Path(__file__).with_name("interface.html")).read_bytes()
MAX_PROFILE_BYTES = 1024 * 1024


class InterfaceServer(ThreadingHTTPServer):
    """只绑定本机的页面和任务 API（应用程序接口）。"""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, server_address, output_root: Path, *, task_options=None):
        super().__init__(server_address, InterfaceHandler)
        self.output_root = Path(output_root).resolve()
        self.task_options = dict(task_options or {})
        self.task_root = self.output_root / "tasks"
        self.input_root = self.output_root / "inputs"
        self.task_root.mkdir(parents=True, exist_ok=True)
        self.input_root.mkdir(parents=True, exist_ok=True)
        self.tasks: dict[str, tuple[Path, object]] = {}
        self.tasks_lock = threading.RLock()

    def task_paths(self, task_id: str) -> tuple[Path, Path]:
        """为服务生成的 ID（标识）返回固定目录，拒绝路径穿越。"""
        if len(task_id) != 32 or any(c not in "0123456789abcdef" for c in task_id):
            raise TaskError("任务编号无效")
        destination = (self.task_root / task_id).resolve()
        input_path = (self.input_root / f"{task_id}.simc").resolve()
        if destination.parent != self.task_root or input_path.parent != self.input_root:
            raise TaskError("任务路径无效")
        return input_path, destination


class InterfaceHandler(BaseHTTPRequestHandler):
    server: InterfaceServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A003
        return

    def _local_request_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        hostname = urlsplit(f"http://{host}").hostname if host else None
        if hostname not in {"127.0.0.1", "localhost"}:
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        expected = {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }
        return origin in expected

    def _send_json(self, status: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_page(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError as error:
            raise TaskError("请求长度无效") from error
        if not 0 <= length <= MAX_PROFILE_BYTES:
            raise TaskError("角色资料过大或请求长度无效")
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise TaskError("请求内容不是有效的 JSON（结构化数据）") from error
        if not isinstance(value, dict):
            raise TaskError("请求内容格式无效")
        return value

    def do_GET(self):  # noqa: N802
        if not self._local_request_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "只允许本机访问"})
            return
        path = urlsplit(self.path).path
        if path == "/":
            self._send_page()
            return
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {"status": "ready"})
            return
        prefix = "/api/tasks/"
        if path.startswith(prefix):
            task_id = path[len(prefix):].rstrip("/")
            try:
                _, destination = self.server.task_paths(task_id)
                with self.server.tasks_lock:
                    entry = self.server.tasks.get(task_id)
                state = self._read_public_state(destination, entry)
            except (TaskError, OSError, ValueError) as error:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
                return
            self._send_json(HTTPStatus.OK, state)
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "页面不存在"})

    def do_POST(self):  # noqa: N802
        if not self._local_request_allowed():
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "只允许本机访问"})
            return
        path = urlsplit(self.path).path
        try:
            if path == "/api/gse/inspect":
                from gse_import import inspect_import
                value = self._body()
                try:
                    inspected = inspect_import(value.get("gse"))
                except ValueError as error:
                    raise TaskError(str(error)) from error
                self._send_json(HTTPStatus.OK, inspected)
                return
            if path == "/api/tasks":
                self._create_task()
                return
            prefix = "/api/tasks/"
            if path.startswith(prefix):
                task_id, action = path[len(prefix):].rstrip("/").split("/", 1)
                if action == "cancel":
                    self._change_task(task_id)
                    return
            raise TaskError("接口不存在")
        except TaskError as error:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": _friendly_error(error)})
        except (OSError, ValueError) as error:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": _friendly_error(error)})

    def _create_task(self) -> None:
        value = self._body()
        mode = value.get("mode", "optimize")
        if mode not in ("optimize", "import"):
            raise TaskError("任务模式无效")
        profile = value.get("profile")
        if not isinstance(profile, str) or not profile.strip():
            raise TaskError("请先粘贴角色导出字符串")
        if len(profile.encode("utf-8")) > MAX_PROFILE_BYTES:
            raise TaskError("角色资料过大")
        interval = value.get("input_interval_ms", 300)
        if type(interval) is not int or not 50 <= interval <= 2000:
            raise TaskError("按键间隔必须为 50 至 2000 毫秒的整数")
        options = dict(self.server.task_options)
        options['search_config'] = dict(options.get('search_config') or {}, input_interval_ms=interval)
        if mode == "import":
            from gse_import import decode_import, inspect_import
            gse = value.get("gse")
            name = value.get("sequence_name")
            version = value.get("version")
            click_ms = value.get("gse_click_ms")
            gcd_ms = value.get("gcd_ms")
            if not isinstance(name, str) or not name or type(version) is not int:
                raise TaskError("GSE 导入需要选定序列与版本")
            try:
                imported = decode_import(gse)
                inspected = inspect_import(gse, decoded=imported)
            except ValueError as error:
                raise TaskError(str(error)) from error
            if name not in imported["sequences"]:
                raise TaskError("GSE 选定的序列或版本无效")
            member = next((row for row in inspected["sequences"] if row["name"] == name), None)
            support = (next((row for row in member["version_support"] if row["version"] == version), None)
                       if member is not None else None)
            if support is None:
                raise TaskError("GSE 选定的序列或版本无效")
            if not support["simulation_preflight_passed"]:
                raise TaskError(support["support_reason"])
            if type(click_ms) is not int or not 50 <= click_ms <= 2000:
                raise TaskError("GSE 点击间隔必须为 50 至 2000 毫秒")
            if click_ms != interval:
                raise TaskError("GSE 点击间隔必须与模拟按键间隔一致")
            if type(gcd_ms) is not int or not 500 <= gcd_ms <= 3000:
                raise TaskError("GSE 公共冷却必须为 500 至 3000 毫秒")
            options.update(mode="import", gse_text=gse, sequence_name=name, version=version,
                           gse_context=dict(click_ms=interval, input_interval_ms=interval,
                                            gcd_ms=gcd_ms, seed=20260912, pet_ready=True,
                                            enemy_target_ready=True))
        parse_character(profile)
        task_id = uuid.uuid4().hex
        input_path, destination = self.server.task_paths(task_id)
        input_path.write_text(profile, encoding="utf-8", newline="")
        try:
            handle = start_task(input_path, destination, **options)
        except BaseException:
            input_path.unlink(missing_ok=True)
            raise
        with self.server.tasks_lock:
            self.server.tasks[task_id] = (destination, handle)
        self._send_json(HTTPStatus.ACCEPTED, {"task_id": task_id, "status": "starting"})

    def _read_public_state(self, destination: Path, entry) -> dict:
        try:
            return _public_state(read_task(destination), destination)
        except TaskError as error:
            handle = entry[1] if entry else None
            if handle is not None and not handle.done:
                return _starting_state()
            if handle is not None and handle.error is not None:
                return {
                    "status": "failed",
                    "phase": "done",
                    "progress": 0.0,
                    "elapsed_seconds": getattr(handle.runtime, "elapsed_seconds", 0.0),
                    "completed_batches": 0,
                    "result_ready": False,
                    "error": _friendly_error(handle.error),
                }
            raise error

    def _change_task(self, task_id: str) -> None:
        _, destination = self.server.task_paths(task_id)
        with self.server.tasks_lock:
            entry = self.server.tasks.get(task_id)
        state = cancel_task(entry[1] if entry else destination)
        self._send_json(HTTPStatus.OK, _public_state(state, destination))


def _starting_state() -> dict:
    return {
        "status": "starting",
        "phase": "initialize",
        "elapsed_seconds": 0.0,
        "total_budget_seconds": 600.0,
        "progress": 0.0,
        "completed_batches": 0,
        "result_ready": False,
    }


def _friendly_error(error: BaseException) -> str:
    message = str(error).strip()
    if message.startswith('GSE '):
        return message.splitlines()[0][:160]
    if message.startswith('原生未提供此角色的伤害模拟'):
        return '原生未提供此角色的伤害模拟，请查看任务中的原生报告。'
    if '主动能力不完整' in message:
        return '当前角色包含尚未支持的主动能力，请保留角色导出文本并反馈。'
    if any(token in message for token in ("编译", "编码", "导出")) and "角色导出" not in message:
        return "导出校验失败，请检查本机编译环境后重试。"
    if "原生引擎" in message:
        return "引擎计算失败，请检查本机模拟环境后重试。"
    if isinstance(error, TaskError) and message:
        if any(token in message for token in ("角色", "字段", "输入", "专精", "职业")):
            return message.splitlines()[0][:160] + "，请检查角色导出内容后重试。"
        return message.splitlines()[0][:160]
    if isinstance(error, ImportError):
        return "任务依赖未准备好，请检查本机依赖后重试。"
    if isinstance(error, OSError):
        return "本机文件或模拟环境不可用，请检查准备状态后重试。"
    if message and "超时" in message:
        return "模拟计算超时，请检查本机模拟环境后重试。"
    return "引擎计算失败，请检查本机模拟环境后重试。"


def _public_state(state: dict, destination: Path) -> dict:
    """把真实任务事件转为页面所需的少量状态；结果就绪前不读取候选文本。"""
    status = state.get("status", "starting")
    phase = state.get("phase", "initialize")
    budget = float((state.get("config") or {}).get("total_budget_seconds", 600))
    elapsed = max(0.0, float(state.get("elapsed_seconds", 0)))
    response = {
        "status": status,
        "phase": "done" if phase in ("done", "complete") else phase,
        "elapsed_seconds": elapsed,
        "total_budget_seconds": budget,
        "progress": min(1.0, elapsed / budget) if budget else 0.0,
        "completed_batches": int(state.get("completed_batches", 0) or 0),
        "input_interval_ms": (state.get("config") or {}).get("input_interval_ms", 300),
    }
    if state.get("error"):
        response["error"] = _friendly_error(TaskError(str(state["error"])))
    if status == "completed" and (state.get("candidate") or {}).get("source") == "gse":
        candidate = state["candidate"]
        response.update(selected_sequence=candidate["selected_sequence"],
                        selected_version=candidate["selected_version"],
                        import_sha256=candidate["import_sha256"],
                        dps=state["controlled_simulation"]["summary"]["dps"],
                        result_ready=False, simulation_ready=True, progress=1.0)
        return response
    if status in ("completed", "validation_incomplete"):
        candidate_path = destination / "candidate.txt"
        if candidate_path.is_file():
            text = candidate_path.read_text(encoding="ascii").strip()
            expected = (state.get("candidate") or {}).get("text")
            if text and expected == text:
                response.update(
                    result_ready=True,
                    candidate_text=text,
                    evidence_status=("complete" if state.get("independent_validation_complete")
                                      else "insufficient_validation"),
                )
                if status == "validation_incomplete" and state.get("improvement") == "not_proven_better":
                    response["result_note"] = (
                        "复测未完成；已保留锁定候选，不能视为验证通过。"
                        if state.get("locked_candidate_key") == state.get("selected_candidate_key")
                        else "复测未完成；未证明优于初始序列，已保留初始序列。"
                    )
                elif state.get("improvement") == "not_proven_better":
                    response["result_note"] = "未证明优于初始序列，已保留初始序列。"
                elif status == "validation_incomplete":
                    response["result_note"] = "复测未完成，结果仅供查看，不能视为验证通过。"
                return response
        response.update(status="failed", error="结果文件缺失，未生成可复制文本")
    response.setdefault("result_ready", False)
    return response


def create_server(output_root: str | Path, *, host: str = "127.0.0.1", port: int = 0,
                  task_options=None) -> InterfaceServer:
    """创建本地服务；`port=0` 由系统分配空闲端口。"""
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("界面服务只能绑定本机地址")
    return InterfaceServer((host, port), Path(output_root), task_options=task_options)


def serve(output_root: str | Path, *, host: str = "127.0.0.1", port: int = 8780,
          task_options=None) -> None:
    server = create_server(output_root, host=host, port=port, task_options=task_options)
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = ["InterfaceServer", "create_server", "serve"]
