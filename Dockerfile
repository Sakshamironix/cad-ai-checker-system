# Development container for GitHub Codespaces.
# CadQuery is installed from conda-forge because it bundles compatible OpenCASCADE libraries.
FROM mcr.microsoft.com/devcontainers/miniconda:1-3

ARG CONDA_ENV=cad-ai-checker

RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY environment.yml /tmp/environment.yml

RUN conda env create --file /tmp/environment.yml \
    && conda clean --all --yes

ENV CONDA_DEFAULT_ENV=${CONDA_ENV}
ENV PATH=/opt/conda/envs/${CONDA_ENV}/bin:${PATH}

RUN echo "conda activate ${CONDA_ENV}" >> /home/vscode/.bashrc

USER vscode
