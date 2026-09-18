FROM python:3.12-slim

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
RUN pip install --no-cache-dir httpx
COPY golden_dataset.json run_eval.py ./
USER appuser
CMD ["python", "run_eval.py"]