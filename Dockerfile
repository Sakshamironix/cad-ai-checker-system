# Restartable Milestone 16 pilot container. CadQuery bundles compatible OpenCASCADE.
FROM mcr.microsoft.com/devcontainers/miniconda:1-3

ARG CONDA_ENV=cad-ai-checker

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY environment.yml /tmp/environment.yml

RUN conda env create --file /tmp/environment.yml \
    && conda clean --all --yes

WORKDIR /app
COPY --chown=vscode:vscode . /app

ENV CONDA_DEFAULT_ENV=${CONDA_ENV} \
    PATH=/opt/conda/envs/${CONDA_ENV}/bin:${PATH} \
    PORT=8501

RUN echo "conda activate ${CONDA_ENV}" >> /home/vscode/.bashrc

USER vscode
RUN chmod +x /app/scripts/start.sh /app/scripts/healthcheck.py

EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 CMD python /app/scripts/healthcheck.py
CMD ["/app/scripts/start.sh"]
