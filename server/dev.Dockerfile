FROM python:3.12

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y libpq5 && rm -rf /var/lib/apt/lists/*

# Copy and install server requirements
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install mem0 SDK from local source
COPY pyproject.toml README.md LICENSE ./
COPY mem0 ./mem0
RUN pip install --no-cache-dir -e .

# Copy server code
COPY server .

EXPOSE 8000
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
