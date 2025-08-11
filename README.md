# Youtube2Bilibili 自动化搬运器

本项目根据多个关键词搜索 YouTube，查重 B 站后，调用本地 VideoLingo FastAPI（见 `api_server.py`）进行自动加字幕/翻译，再使用 `biliup` 命令行上传到 B 站。标题/标签/描述通过兼容 OpenAI 格式的接口自动生成。

## 目录结构
- `api_server.py`：你提供的 VideoLingo API 服务。
- `config/settings.json`：配置文件（可复制 `settings.example.json`）。
- `services/`：功能模块（搜索、调用 API、生成标题标签、查重）。
- `scripts/auto_runner.py`：主入口脚本。
- `workspace/`：下载/封面/缓存目录。
 - `workspace/history.jsonl`：已上传历史记录（每行一条 JSON）。

## 依赖
- Python 3.9+
- `yt-dlp`（用于搜索/封面）
- `biliup`（命令行上传）
- `requests`

推荐安装：
```
pip install -U yt-dlp requests
# biliup 请参考其官方安装说明
```

## 配置
复制示例：
```
cp config/settings.example.json config/settings.json
```
按需修改：
- `api_base`：VideoLingo API 地址（启动 `api_server.py` 后默认 `http://127.0.0.1:8000`）。
- `openai`：你兼容 OpenAI 的接口地址、Key、模型。
- `youtube`：搜索参数。
- `bilibili.duplicate_threshold`：查重阈值（0-1）。目前查重函数为占位实现，默认为不拦截。
- `paths`：本地工作目录。
- `history_file`：历史记录文件（默认 `workspace/history.jsonl`）。
- `cleanup_remote`：是否在任务完成后删除远端任务及其缓存（默认开启）。
- `upload_retry_attempts` / `upload_retry_backoff_sec`：上传失败的重试次数与初始退避秒数（默认 3 次、20 秒）。
- 新增 `keywords`：关键词数组，例如：
```
{
  "keywords": ["AI 指南", "Python 教程"],
  ... 其他配置 ...
}
```

## 运行
1. 先启动 VideoLingo API：
```
python api_server.py
```
2. 运行自动脚本：
```
python scripts/auto_runner.py
```

## 说明
- 本项目不使用 YouTube 官方 API，搜索由 `yt-dlp` 实现，结果可能不稳定。
- B 站查重模块当前提供占位实现（始终返回无重复），可接入更强的搜索或相似度算法。
- 上传依赖你已配置好的 `biliup` 登录状态与 Cookie。
- 若启用配音，将在服务端生成配音并可下载 `video_dub`。
- 历史去重：脚本会读取 `history_file` 跳过已处理的 YouTube 视频 ID；成功上传后追加记录。

## 风险与合规
- 请确保你拥有转载视频的授权或遵循平台规则与版权政策。
- 生成内容请遵循平台社区规范，避免敏感与违规信息。
