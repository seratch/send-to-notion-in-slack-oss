#
# docker build . -t your-repo/send-to-notion
# export SLACK_APP_TOKEN=xapp-...
# export SLACK_BOT_TOKEN=xoxb-...
# export NOTION_API_TOKEN=secret_...
# docker run -e SLACK_APP_TOKEN=$SLACK_APP_TOKEN -e SLACK_BOT_TOKEN=$SLACK_BOT_TOKEN -e NOTION_API_TOKEN=$NOTION_API_TOKEN -it your-repo/send-to-notion
#
FROM python:3.11.0-slim-bullseye
RUN apt-get update && apt-get clean
COPY requirements.txt /root/
COPY *.py /root/
COPY app/ /root/app
WORKDIR /root/
RUN pip install -U pip && pip install -r requirements.txt
ENTRYPOINT python main.py
