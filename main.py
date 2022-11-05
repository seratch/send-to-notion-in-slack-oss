import logging
import os
from typing import Callable
from slack_bolt import App, BoltContext
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.slack_events import register_slack_event_handlers
from dotenv import load_dotenv

load_dotenv()

slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
slack_app_level_token = os.environ.get("SLACK_APP_TOKEN")
notion_api_token = os.environ.get("NOTION_API_TOKEN")

app = App(token=slack_bot_token)


@app.middleware
def attach_notion_token(context: BoltContext, next_: Callable):
    context["notion_token"] = notion_api_token
    next_()


register_slack_event_handlers(app)

if __name__ == "__main__":
    logging.basicConfig(format="%(asctime)s %(message)s", level=logging.DEBUG)
    SocketModeHandler(app, slack_app_level_token).start()
