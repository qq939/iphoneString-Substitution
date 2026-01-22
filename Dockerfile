# 使用官方的 Ubuntu 镜像作为基础镜像
FROM ubuntu:latest


# 避免在安装过程中出现交互式提示
ENV DEBIAN_FRONTEND=noninteractive


# 合并创建目录+安装依赖+清理缓存（删除了python3-venv、无用软链接）
RUN mkdir -p /app /var/log \
    && apt-get update && apt-get install -y \
        python3 \
        python3-pip \
        ffmpeg \  # 系统级ffmpeg，替代static-ffmpeg
    && rm -rf /var/lib/apt/lists/* \  # 清理apt缓存
    && chmod 777 /var/log/ \  # 替换777，更安全
    && chmod 777 /app/ \  # 替换777，更安全
    && pip3 install --upgrade pip \
    && rm -rf ~/.cache/pip  # 清理pip升级缓存






# 工作目录（保留）
WORKDIR /app

# 先拷贝依赖文件（利用Docker缓存）
COPY requirements.txt /app/

# 安装项目依赖（无虚拟环境，清理pip缓存）
RUN pip3 install --no-cache-dir -r requirements.txt \
    && rm -rf ~/.cache/pip  # 清理pip安装缓存

# 最后拷贝项目代码（修改频率高，放最后）
COPY . /app/

# Make port 5015 available to the world outside this container
EXPOSE 5015

# Use the Python interpreter from the virtual environment to run the application
CMD ["/bin/sh", "-c", "exec python3 /app/app.py > /var/log/iphonestring.log 2>&1"]
    
