FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /pipeline

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY cli.py ./
COPY safety_config.py ./
COPY streetlight_config.py ./
COPY safety_component_config.py ./
COPY pytest.ini ./
COPY collectors ./collectors
COPY preprocess ./preprocess
COPY loaders ./loaders
COPY analysis ./analysis
COPY config ./config
COPY tests ./tests

ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
