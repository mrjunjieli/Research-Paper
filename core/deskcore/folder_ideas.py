"""Private research ideas attached to stable favorite-folder IDs."""
from datetime import datetime, timezone

MAX_CONTENT = 100000

def init(conn):
    with conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS folder_ideas(folder_id TEXT PRIMARY KEY,content TEXT NOT NULL,revision INTEGER NOT NULL,updated TEXT NOT NULL)')

def _folder(c, fid):
    if not isinstance(fid, str) or not fid or not c.execute('SELECT 1 FROM favorite_folders WHERE id=?', (fid,)).fetchone():
        raise ValueError('请选择一个已创建的收藏夹')

def _read(c, fid):
    row = c.execute('SELECT * FROM folder_ideas WHERE folder_id=?', (fid,)).fetchone()
    return dict(row) if row else dict(folder_id=fid, content='', revision=0, updated='')

def read(conn, fid):
    with conn() as c:
        _folder(c, fid)
        return _read(c, fid)

def save(conn, payload):
    fid, content, revision = payload.get('folder_id'), payload.get('content'), payload.get('revision')
    if not isinstance(content, str) or len(content) > MAX_CONTENT:
        raise ValueError('研究想法应为文本，最多 100000 字')
    if type(revision) is not int or revision < 0:
        raise ValueError('缺少有效版本，请重新加载后重试')
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        _folder(c, fid)
        current = _read(c, fid)
        # A retry after a lost response is safe and does not create another revision.
        if content == current['content']:
            return current, 200
        if revision != current['revision']:
            return {'error': '另一页面已修改这份记录；你的草稿已保留，请先复制草稿再加载已保存版本。', 'conflict': True}, 409
        updated = datetime.now(timezone.utc).isoformat()
        c.execute('INSERT INTO folder_ideas VALUES(?,?,?,?) ON CONFLICT(folder_id) DO UPDATE SET content=excluded.content,revision=excluded.revision,updated=excluded.updated',
                  (fid, content, revision + 1, updated))
        return _read(c, fid), 200
