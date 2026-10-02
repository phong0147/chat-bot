FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py cli.py ./
COPY ingestion/ ./ingestion/
COPY upload/ ./upload/
ENTRYPOINT ["python", "main.py"]
