# Youtube2Bilibili 自动化搬运器

本项目根据多个关键词搜索 YouTube，查重 B 站后，调用本地 VideoLingo FastAPI（见 `api_server.py`）进行自动加字幕/翻译，再使用 `biliup` 命令行上传到 B 站。标题/标签/描述通过兼容 OpenAI 格式的接口自动生成。

## 使用
```bash
docker run -itd --name Youtube2Bilibili --link Videolingo \
  -v /Docker/youtube2bilibili/config:/app/config \
  -v /Docker/youtube2bilibili/workspace:/app/workspace \
  -e http_proxy="http://192.168.1.100:7890" -e https_proxy="http://192.168.1.100:7890" \
  -e NO_PROXY="Videolingo,127.0.0.1,localhost" -e no_proxy="Videolingo,127.0.0.1,localhost" \
  --restart always yht0511/youtube2bilibili:latest
```