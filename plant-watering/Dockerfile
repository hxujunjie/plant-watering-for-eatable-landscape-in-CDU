FROM python:3.10-slim

# 创建用户（HF Spaces 要求 UID 1000）
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# 安装依赖
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY --chown=user app.py database.py .
COPY --chown=user templates/ templates/
COPY --chown=user static/ static/

# 数据持久化到 /data（HF Spaces 提供的持久化目录）
RUN mkdir -p /data/uploads && chmod 777 /data
ENV UPLOAD_DIR=/data/uploads
ENV DB_PATH=/data/watering.db
ENV PORT=7860

EXPOSE 7860

USER user

CMD ["python", "app.py"]
