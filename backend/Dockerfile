FROM python:3.12-slim

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# api e worker non girano come root; /data esiste già con il proprietario giusto,
# così anche un volume nuovo (es. quello di make e2e) nasce scrivibile
RUN useradd --create-home --uid 1000 earnsight \
    && mkdir -p /data \
    && chown earnsight:earnsight /data
USER earnsight

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
