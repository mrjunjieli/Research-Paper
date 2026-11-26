"""deskcore.runtime — 启动与装配。

综合项目和各子项目的入口都只调用这里：
  load_projects([...])  → 逐个导入子项目（失败只记录，不影响其他项目）
  serve(port, index=...) → 初始化数据库、启动后台线程、开始监听
"""
import importlib
import os
import sys
import threading
from pathlib import Path

from deskcore import hooks

CORE_DIR = Path(__file__).resolve().parent


def add_paths(*paths):
    for path in reversed(paths):
        path = str(path)
        if path not in sys.path:
            sys.path.insert(0, path)


def _register_static(directory):
    directory = Path(directory)
    if not directory.is_dir():
        return
    for file in directory.iterdir():
        if file.is_file():
            hooks.STATIC.setdefault('/' + file.name, str(file.resolve()))


def build_static(index_files=None, project_dirs=None):
    hooks.STATIC.clear()
    _register_static(CORE_DIR / 'static')
    for directory in project_dirs or []:
        _register_static(directory)
    for url, file in (index_files or {}).items():
        hooks.STATIC[url] = str(Path(file).resolve())


def load_projects(entries):
    """entries: [(project_id, module_path, display_name, static_dir)] — 导入失败会降级。"""
    for project_id, module_path, name, static_dir in entries:
        try:
            importlib.import_module(module_path)
            hooks.register_project(project_id, name, static_dir)
        except Exception as exc:
            hooks.register_project(project_id, name, static_dir, ok=False, error=type(exc).__name__ + ': ' + str(exc)[:300])
            hooks.record_failure('import', exc, project_id)


def _start_background(engine):
    workers = max(1, min(3, int(os.environ.get('KNOWLEDGE_REVIEW_WORKERS', '1'))))
    for _ in range(workers):
        threading.Thread(target=engine.worker, daemon=True).start()
    threading.Thread(target=engine.scheduler, daemon=True).start()
    for fn in hooks.START:
        try:
            fn()
        except Exception as exc:
            hooks.record_failure('start', exc)


def serve(port=8765, index_files=None, project_dirs=None):
    from deskcore import engine
    from deskcore.http import Handler
    from http.server import ThreadingHTTPServer

    build_static(index_files, project_dirs)
    engine.init()
    engine.ui_reads.initialize(engine.enrichment_desk())
    engine.DELIVERY.initialize(engine.enrichment_desk())
    _start_background(engine)
    server = ThreadingHTTPServer(('127.0.0.1', int(port)), Handler)
    print('Knowledge Desk: http://127.0.0.1:%d' % port, flush=True)
    server.serve_forever()


def task_center_records():
    """任务中心的额外来源（例如论文处理队列）由项目注册。"""
    records = []
    for fn in hooks.TASKS:
        try:
            records.extend(fn() or [])
        except Exception as exc:
            hooks.record_failure('task-provider', exc)
    return records
