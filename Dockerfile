FROM python:3.12-slim
WORKDIR /app
COPY app ./app
COPY web ./web
COPY data ./data
COPY tests/fixtures ./tests/fixtures
RUN useradd --create-home pf && chown -R pf /app
USER pf
ENV PLUSFACTOR_HOSTED=1 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "app.server"]
