# 1. 基础镜像
# 原华为云 SWR 加速镜像解包后文件为空（exec format error），改用 DaoCloud 镜像源
FROM docker.m.daocloud.io/library/python:3.12-slim

# 2. 设置环境变量
# 防止 Python 写 .pyc 文件
ENV PYTHONDONTWRITEBYTECODE=1
# 保证控制台输出不被缓冲，方便看日志
ENV PYTHONUNBUFFERED=1
# 设置时区为上海
ENV TZ=Asia/Shanghai

# 3. 设置工作目录
WORKDIR /app

# 4. 先复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple

# 5. 复制项目代码
COPY . .

# 6. 确保 data 目录存在
RUN mkdir -p data

# 7. 暴露端口
EXPOSE 8000

# 8. 启动命令
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]