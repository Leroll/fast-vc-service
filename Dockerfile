FROM leroll/cuda:12.2.2-cudnn8-devel-ubuntu22.04-py3.10

WORKDIR /app

# set timezone 
ENV TZ=Asia/Shanghai
ENV DEBIAN_FRONTEND=noninteractive

# Disable Python output buffering for real-time logs in Docker
ENV PYTHONUNBUFFERED=1  
# Disable Poetry interactive prompts for automated builds
ENV POETRY_NO_INTERACTION=1
# Create virtual environment inside project directory
ENV POETRY_VENV_IN_PROJECT=1
# Set Poetry cache directory for easy cleanup
ENV POETRY_CACHE_DIR=/tmp/poetry_cache
# Set Poetry installation directory
ENV POETRY_HOME="/opt/poetry"
# Pin Poetry version for consistent builds
ENV POETRY_VERSION=2.1.3

# Install System Dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    libsndfile1 \
    libopus0 \
    libopus-dev \
    portaudio19-dev \
    libasound2-dev \
    ffmpeg \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies using Poetry
RUN pip install poetry==$POETRY_VERSION
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-root \
    && rm -rf $POETRY_CACHE_DIR

# Install Fast-vc
COPY . .
RUN cp .env.example .env
RUN poetry install
RUN chmod +x /app

EXPOSE 8042

CMD ["fast-vc", "serve"]
