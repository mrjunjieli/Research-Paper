"""项目注册与隔离边界。

每个子项目在导入时调用 register_* 把路由、静态文件、初始化和启动钩子交给内核。
某个项目导入失败或某个路由抛异常时，只影响该项目自己：内核记录失败信息，
其余页面和接口继续工作，前端仍能正常渲染。
"""
import json
import traceback

PROJECTS = {}          # id -> {'id','name','ok','error','static'}
STATIC = {}            # url -> 绝对路径
MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'application/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.json': 'application/json; charset=utf-8',
    '.png': 'image/png',
    '.woff2': 'font/woff2',
    '.woff': 'font/woff',
    '.ttf': 'font/ttf',
}
INIT = []              # fn(desk) — 建表等幂等初始化
START = []             # fn() — 服务启动后的后台线程
GET_ROUTES = {}        # path -> (project_id, fn(handler, payload))
POST_ROUTES = {}
PREFIX_GET = []        # (regex, project_id, fn(handler, payload, match))
TASKS = []             # fn() -> list[dict] — 任务中心的额外来源
FAILURES = []          # [{'stage','project','error','frames'}]
RAW = object()         # 路由已自行写出响应（例如图片字节），dispatch 不再包装成 JSON


def register_project(project_id, name, static_dir=None, ok=True, error=''):
    PROJECTS[project_id] = {'id': project_id, 'name': name, 'ok': ok, 'error': error, 'static': static_dir}


def record_failure(stage, exc, project=''):
    frames = [{'file': f.filename.rsplit('/', 1)[-1], 'line': f.lineno, 'function': f.name}
              for f in traceback.extract_tb(getattr(exc, '__traceback__', None))][-6:]
    item = {'stage': stage, 'project': project, 'error': type(exc).__name__ + ': ' + str(exc)[:300], 'frames': frames}
    FAILURES.append(item)
    print(json.dumps({'event': 'project_failure', **item}, ensure_ascii=False), flush=True)
    if project in PROJECTS:
        PROJECTS[project]['ok'] = False
        PROJECTS[project]['error'] = item['error']


def register_get(path, fn, project):
    GET_ROUTES[path] = (project, fn)


def register_post(path, fn, project):
    POST_ROUTES[path] = (project, fn)


def register_prefix(regex, fn, project):
    PREFIX_GET.append((regex, project, fn))


def dispatch(handler, method, path, payload):
    """返回 True 表示该请求已由某个项目处理（含出错时的降级响应）。"""
    table = GET_ROUTES if method == 'GET' else POST_ROUTES
    entry = table.get(path)
    match = None
    if not entry:
        for regex, project, fn in PREFIX_GET:
            found = regex.fullmatch(path) if hasattr(regex, 'fullmatch') else None
            if found:
                entry = (project, fn)
                match = found
                break
    if not entry:
        return False
    project, fn = entry
    try:
        result = fn(handler, payload) if match is None else fn(handler, payload, match)
        if result is RAW:
            return True
        if isinstance(result, tuple):
            handler.reply(result[0], result[1])
        else:
            handler.reply(result)
    except (BrokenPipeError, ConnectionResetError):
        pass
    except (ValueError, KeyError, TypeError) as exc:
        try:
            handler.reply({'error': str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
    except Exception as exc:
        record_failure('route', exc, project)
        try:
            handler.reply({'error': '「%s」暂时不可用，其他页面不受影响。' % PROJECTS.get(project, {}).get('name', project)}, 503)
        except (BrokenPipeError, ConnectionResetError):
            pass
    return True


def projects_payload():
    return {'projects': [{'id': p['id'], 'name': p['name'], 'ok': p['ok'], 'error': p['error']}
                         for p in PROJECTS.values()],
            'failures': FAILURES[-10:]}
