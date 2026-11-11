FROM python:3.11-slim

# Ustawienie katalogu roboczego wewnątrz kontenera
WORKDIR /app

# Zmienne środowiskowe optymalizujące działanie Pythona w kontenerze
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Instalacja zależności
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Skopiowanie kodu aplikacji
COPY . .

# Wystawienie portu i uruchomienie serwera Uvicorn
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]