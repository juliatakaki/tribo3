# Imagem do serviço `seed` do docker-compose: gera a massa sintética e
# roda o pipeline de qualidade assim que as migrations terminam.
#
# As dependências são instaladas na build, não no command: instalar a
# cada `up` seria lento e quebraria sem rede.

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

CMD ["python", "seed.py"]
