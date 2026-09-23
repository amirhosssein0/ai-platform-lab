FROM python:3.12-slim

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
RUN pip install --no-cache-dir httpx
COPY eval/golden_dataset.json eval/run_eval.py ./
COPY prompts ./prompts
USER appuser
CMD ["python", "run_eval.py"]