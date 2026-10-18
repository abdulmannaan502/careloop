FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY careloop ./careloop
RUN pip install --no-cache-dir .
ENV HOST=0.0.0.0 PORT=8000
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["careloop"]
