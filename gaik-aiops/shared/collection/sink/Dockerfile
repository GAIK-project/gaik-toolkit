FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY collection_sink ./collection_sink
RUN pip install --no-cache-dir . && useradd --uid 10001 --no-create-home sink
USER 10001
EXPOSE 4319
CMD ["collection-sink"]
