FROM python:3.7
WORKDIR /src
COPY requirements.txt /config/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r /config/requirements.txt