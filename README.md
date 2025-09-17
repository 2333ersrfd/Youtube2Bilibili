# Youtube2Bilibili 自动化搬运器

本项目根据多个关键词搜索 YouTube，查重 B 站后，调用本地 VideoLingo FastAPI（见 `api_server.py`）进行自动加字幕/翻译，再使用 `biliup` 命令行上传到 B 站。标题/标签/描述通过兼容 OpenAI 格式的接口自动生成。

## 使用
克隆仓库
docker 下载videolingo镜像，创建容器
配置settings.json文件
挂载文件夹

可能会遇到的问题：
运行videolingo后，打开web页面，调用api；
安装ping命令
bash
docker exec -it your-container-name /bin/bash
apt-get update && apt-get install -y iputils-ping

添加biliup到系统环境
