FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY . .
RUN groupadd --gid 10001 chubby && useradd --uid 10001 --gid chubby --no-create-home chubby \
    && mkdir /private-evidence && chown chubby:chubby /private-evidence && chmod 700 /private-evidence
USER chubby
EXPOSE 8000
