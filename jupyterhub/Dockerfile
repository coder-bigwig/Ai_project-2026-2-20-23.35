FROM jupyterhub/jupyterhub:4.0.0

# 安装必要的依赖
RUN pip install \
    dockerspawner \
    jupyterhub-idle-culler \
    oauthenticator \
    psycopg2-binary

# 创建配置目录
RUN mkdir -p /srv/jupyterhub

# 设置工作目录
WORKDIR /srv/jupyterhub

# 复制配置文件
COPY jupyterhub_config.py /srv/jupyterhub/jupyterhub_config.py

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["jupyterhub", "-f", "/srv/jupyterhub/jupyterhub_config.py"]
