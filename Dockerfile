FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt* requirements* ./
RUN if [ -f requirements.txt ]; then pip install -r requirements.txt; else pip install -r requirements; fi
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main_v20:app", "--host", "0.0.0.0", "--port", "8000"]