FROM python:3.10 AS requirements_stage

WORKDIR /wheel

RUN python -m pip install --user pipx

COPY ./pyproject.toml ./README.md \
  /wheel/

RUN pip install .

RUN python -m pipx run --no-cache nb-cli generate -f /tmp/bot.py


FROM python:3.10-slim

WORKDIR /app

ENV TZ=Asia/Shanghai
ENV PYTHONPATH=/app

COPY ./docker/gunicorn_conf.py ./docker/start.sh /
RUN chmod +x /start.sh

ENV APP_MODULE=_main:app
ENV MAX_WORKERS=1

COPY --from=requirements_stage /tmp/bot.py /app
COPY ./docker/_main.py /app
COPY pyproject.toml README.md /app/

# Combine pip installs
RUN pip install --no-cache-dir gunicorn uvicorn[standard] && \
    pip install --no-cache-dir .

# Combine apt install, playwright install, and cleanup to reduce image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends fonts-noto-cjk libegl1 libgl1 ffmpeg && \
    playwright install chromium && \
    playwright install-deps chromium && \
    rm -rf /var/lib/apt/lists/*

COPY . /app/

CMD ["/start.sh"]