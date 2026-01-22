# 使用官方的 Ubuntu 镜像作为基础镜像
FROM ubuntu:latest


# 避免在安装过程中出现交互式提示
ENV DEBIAN_FRONTEND=noninteractive


# 合并创建目录+安装依赖+清理缓存（删除了python3-venv、无用软链接）
RUN mkdir -p /app /var/log \
    && apt-get update && apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && chmod 777 /var/log/ \
    && chmod 777 /app/



# 工作目录
WORKDIR /app

# 第二步：先创建虚拟环境（关键！避开系统pip保护）
RUN python3 -m venv /app/venv

# 第三步：用虚拟环境的pip升级pip（不再用系统pip3）
RUN /app/venv/bin/pip install --upgrade pip \
    && rm -rf ~/.cache/pip

# 先拷贝依赖文件，利用Docker缓存
COPY requirements.txt /app/

# 用虚拟环境的pip安装项目依赖
RUN /app/venv/bin/pip install --no-cache-dir -r /app/requirements.txt \
    && rm -rf ~/.cache/pip

# 最后拷贝项目代码
COPY . /app/

# 暴露端口
EXPOSE 5015

# 用虚拟环境的python运行程序（和原逻辑一致）
CMD ["/bin/sh", "-c", "exec /app/venv/bin/python /app/app.py > /var/log/iphonestring.log 2>&1"]