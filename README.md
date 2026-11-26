# Research Paper

一个本地论文阅读与研究工作台，从 Knowledge Desk 中独立整理。

包含每日论文采集与推荐、论文库、标签、AI 精读与问答、论文插图、笔记、作者资料、引用关系与研究方向。只加载 Research Paper，不包含新闻、待办、视频创作和实验页面。共用后台仍保留部分兼容代码。

## 本地启动

需要 Python 3.12 或更新版本。此版本在 macOS 上验证；Windows 和 Linux 尚未完成系统验收。

下载仓库 ZIP 并解压，或克隆仓库，然后在项目根目录运行：

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

打开 **http://127.0.0.1:8769/research**。关闭终端中的服务进程后，网站会停止运行。

Windows 使用 `py -3 -m venv .venv` 创建环境，使用 `.venv\Scripts\activate` 激活。Windows / Linux 上请使用下述环境变量提供主模型密钥；当前页面中的密钥持久化依赖 macOS 钥匙串，不支持这两个系统。

## 首次配置

1. 打开“AI 与采集设置”，填写自己的 API 地址、模型名称和密钥，并测试连接。页面提供的模型名称只是预设，请以自己账号实际可用的模型为准。
2. 打开“论文来源”，检查和调整来源及查询。默认领域来源为 `cat:cs.SD OR cat:eess.AS`，热点来源单独列出。可改为自己的研究领域。
3. 设置兴趣主题，手动采集一次，或导入一篇论文。AI 初审、精读及作者补全会使用你配置的服务商额度。
4. 如需每天采集，再启用自动采集并设置时间。电脑必须保持唤醒，且 Python 服务持续运行。

没有 API 密钥也可以启动空白工作台；AI 功能需要自行配置。本项目不附带任何作者的账号或 API 额度。

高级用户可通过 `SUMMARY_API_KEY`、`SUMMARY_BASE_URL`、`SUMMARY_MODEL` 环境变量配置主模型。这些环境变量优先于页面配置。不要把真实密钥写入仓库或提交记录；也不要把密钥填写到 API 地址中。

## 数据与安全

- 首次启动会创建全新的 `data/`，论文、笔记、PDF 和数据库保存在本机，已被 `.gitignore` 排除。
- 本源码包不包含个人数据库、论文、笔记、聊天记录、密钥或历史 Git 提交。
- macOS 页面保存的密钥存入钥匙串，配置文件仅保存引用。环境变量提供的密钥不会自动保存到配置文件。
- 服务只监听 `127.0.0.1`，供本机访问。不要直接作为公开网站部署。
- GitHub 用于分发源码，不会替你运行 Python，也不会让关机后的电脑继续采集。
- 可以用 `KNOWLEDGE_DATA_DIR` 指定独立数据目录，用 `PORT` 更改端口。

## 目录

```text
server.py                  独立启动入口
requirements.txt           PDF 处理依赖
core/deskcore/             共用服务、AI、PDF、界面资源与提示词
projects/research/         论文模块、路由与独立页面
tests/                    隔离的启动和隐私检查
data/                     首次运行生成，不应上传
```

不要只上传 HTML 或 `projects/research/`：运行还需要 `core/`、PDF 依赖和启动入口。接手此仓库的 AI 应先阅读本文件，使用临时数据目录测试，避免写入使用者已有论文库，也不要在未说明的情况下调用付费 API。

## 检查

```sh
python -m unittest discover -s tests -v
```

这些检查不调用付费 AI，不下载远程论文；真实采集、模型调用和第三方可用性需在配置后单独验证。

## 第三方资源

KaTeX 的许可证位于 `core/deskcore/static/katex/LICENSE`。Marked 的 MIT 声明保留在 `core/deskcore/static/marked.js` 中。
