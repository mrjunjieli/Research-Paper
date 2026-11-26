"""研究（Research Paper）子项目。

论文队列、作者情报、引用关系和关系网络属于这个项目；条目读取、采集和
AI 请求来自 deskcore 内核。导入本模块即完成注册，加载失败时
deskcore.hooks 会记录失败，其他项目照常工作。
"""
import threading

from deskcore import engine, hooks
from . import domain
from . import research_directions as DIRECTIONS
from . import routes

NAME = '论文研究'
PROJECT_ID = 'research'

# 内核里对论文模块的调用点（默认是空实现）在这里换成真正的实现。
for _name in ['queue_signature', 'background_signature', 'queue_library_authors', 'enqueue_paper_work',
              'recover_paper_work', 'paper_worker', 'queue_collected_reviews', 'background_review',
              'background_enrichment', 'review_pipeline', 'reconcile_author_profiles',
              'refresh_recommended_authors', 'recover_missing_paper_work', 'enqueue_citation_refresh',
              'refresh_author_metadata', 'citations', 'summarize_author', 'lookup_author', 'merge_authors',
              'graph', 'graph_clusters', 'bounded_graph', 'similar_papers', 'author_list', 'is_library_paper',
              'sync_library_references', 'answer_paper_question', 'paper_note', 'paper_chat_messages',
              'save_author_html', 'save_author_records', 'pdf_author_records']:
    setattr(engine, _name, getattr(domain, _name))

engine.DIRECTIONS = DIRECTIONS


def init(desk):
    DIRECTIONS.init(desk)


def start():
    domain.recover_paper_work()
    for _ in range(2):
        threading.Thread(target=domain.paper_worker, args=('review',), daemon=True).start()
    threading.Thread(target=domain.paper_worker, args=('signature',), daemon=True).start()
    threading.Thread(target=domain.paper_worker, args=('authors',), daemon=True).start()


hooks.INIT.append(init)
hooks.START.append(start)

hooks.register_get('/api/research-directions', routes.get_directions, PROJECT_ID)
hooks.register_get('/api/paper-note', routes.get_paper_note, PROJECT_ID)
hooks.register_get('/api/paper-chat', routes.get_paper_chat, PROJECT_ID)
hooks.register_get('/api/graph', routes.get_graph, PROJECT_ID)

hooks.register_post('/api/paper-note', routes.post_paper_note, PROJECT_ID)
hooks.register_post('/api/paper-chat', routes.post_paper_chat, PROJECT_ID)
hooks.register_post('/api/review', routes.post_review, PROJECT_ID)
hooks.register_post('/api/author-metadata', routes.post_author_metadata, PROJECT_ID)
hooks.register_post('/api/citations', routes.post_citations, PROJECT_ID)
hooks.register_post('/api/account-summary', routes.post_account_summary, PROJECT_ID)
hooks.register_post('/api/author-lookup', routes.post_author_lookup, PROJECT_ID)
hooks.register_post('/api/profile', routes.post_profile, PROJECT_ID)
hooks.register_post('/api/author-merge', routes.post_author_merge, PROJECT_ID)
