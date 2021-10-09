FROM python:3.9
MAINTAINER hullqin
EXPOSE 8000
COPY . /root/poker
WORKDIR /root/poker
RUN pip config set global.index-url https://mirrors.cloud.tencent.com/pypi/simple
RUN pip install -r requirements.txt
CMD daphne -b 0.0.0.0 -p 8000 server:application