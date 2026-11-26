#!/usr/bin/env python3
"""Run the standalone Research Paper workspace."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('KNOWLEDGE_ROOT', str(ROOT))
sys.path[:0] = [str(ROOT / 'core'), str(ROOT)]

from deskcore import runtime, hooks

def main():
    static = ROOT / 'projects/research/static'
    runtime.load_projects([('research', 'projects.research.desk_research', '论文研究', static)])
    runtime.serve(port=int(os.environ.get('PORT', '8769')),
                  index_files={'/': static / 'index.html', '/research': static / 'index.html'},
                  project_dirs=[static])

if __name__ == '__main__':
    main()
