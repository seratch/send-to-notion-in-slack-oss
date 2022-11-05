import json
import logging
import os

from slack_bolt import App, Ack, Say, BoltContext
from slack_sdk import WebClient

from notion_client import Client

from app.notion_ops import (
    find_notion_database,
    build_notion_database_options,
    build_input_blocks,
    send_to_notion,
)


def register_slack_event_handlers(app: App):
    @app.middleware
    def dump(body: dict, logger: logging.Logger, next_):
        logger.debug(body)
        next_()

    #
    # Home tab
    #

    @app.event("app_home_opened")
    def update_home_tab(client: WebClient, context: BoltContext):
        client.views_publish(
            user_id=context.user_id,
            view={
                "type": "home",
                "blocks": [
                    {
                        "type": "section",
                        "block_id": "header",
                        "text": {"type": "mrkdwn", "text": "*Welcome to Send to Notion in Slack* :raised_hands:"},
                    },
                    {
                        "type": "actions",
                        "block_id": "open-modal-button",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Submit data to Notion"},
                                "value": "clicked",
                                "action_id": "open-notion-form",
                            }
                        ],
                    },
                ],
            },
        )

    #
    # Send to Notion
    #

    def build_database_selection_view():
        blocks = [
            {
                "type": "input",
                "block_id": "search-notion-database",
                "element": {
                    "type": "external_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Find a Notion database",
                    },
                    "action_id": "search-notion-database",
                    "min_query_length": 0,
                },
                "label": {"type": "plain_text", "text": "Notion Database"},
            }
        ]

        return {
            "type": "modal",
            "callback_id": "select-notion-database",
            "title": {"type": "plain_text", "text": "Send to Notion"},
            "submit": {"type": "plain_text", "text": "Next"},
            "close": {"type": "plain_text", "text": "Close"},
            "blocks": blocks,
        }

    def resolve_notion_token(context: BoltContext) -> str:
        token = context.get("notion_token")
        if token is None:
            raise Exception("Unexpectedly Notion installation is not found!")
        return token

    @app.action("link-button")
    def just_ack_link_buttons(ack: Ack):
        ack()

    @app.shortcut("open-notion-form")
    @app.action("open-notion-form")
    @app.command("/send-to-notion")
    def open_notion_form(ack: Ack, client: WebClient, body: dict):
        ack()
        client.views_open(
            trigger_id=body["trigger_id"],
            view=build_database_selection_view(),
        )

    @app.action("select-notion-workspace")
    def select_notion_workspace(ack: Ack, body: dict, client: WebClient):
        ack()
        client.views_update(
            view_id=body.get("view").get("id"),
            view=build_database_selection_view(),
        )

    @app.action("go-back-to-database-select-view")
    def go_back_to_initial_modal_view(ack: Ack, client: WebClient, body: dict):
        ack()
        client.views_update(
            view_id=body["view"]["id"],
            hash=body["view"]["hash"],
            view=build_database_selection_view(),
        )

    @app.options("search-notion-database")
    def search_notion_database(ack: Ack, payload: dict, context: BoltContext):
        notion = Client(auth=resolve_notion_token(context))
        options = build_notion_database_options(notion, payload)
        ack(options=options)

    def select_notion_database_ack(ack: Ack):
        ack(
            response_action="update",
            view={
                "type": "modal",
                "callback_id": "select-notion-database",
                "title": {"type": "plain_text", "text": "Send to Notion"},
                "close": {"type": "plain_text", "text": "Close"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ":hourglass: Wait a second. Now loading the database ...",
                        },
                    }
                ],
            },
        )

    def select_notion_database_lazy(
        view: dict,
        client: WebClient,
        say: Say,
        context: BoltContext,
        logger: logging.Logger,
    ):
        try:
            block_key = "search-notion-database"
            database_id = view["state"]["values"][block_key][block_key]["selected_option"]["value"]
            notion = Client(auth=resolve_notion_token(context))
            database = find_notion_database(notion, database_id)
            blocks = build_input_blocks(database)
            client.views_update(
                view_id=view["id"],
                view={
                    "type": "modal",
                    "callback_id": "send-to-notion-database",
                    "title": {"type": "plain_text", "text": "Send to Notion"},
                    "submit": {"type": "plain_text", "text": "Submit"},
                    "close": {"type": "plain_text", "text": "Close"},
                    "private_metadata": json.dumps({"notion_database_id": database_id}),
                    "blocks": blocks,
                },
            )
        except Exception as e:
            logger.exception(e)
            client.views_update(
                view_id=view["id"],
                view={
                    "type": "modal",
                    "callback_id": "send-to-notion-database",
                    "title": {"type": "plain_text", "text": "Send to Notion"},
                    "close": {"type": "plain_text", "text": "Close"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": ":x: Loading Notion database data failed for some reason. "
                                "Please contact this app's user support email address :bow:",
                            },
                        }
                    ],
                },
            )
            say(
                channel=context.user_id,
                text=f"I'm sorry for being distracted! This app encountered a problem (error: {e})\n"
                "Please contact this app's user support email address :bow:",
            )

    app.view("select-notion-database")(
        ack=select_notion_database_ack,
        lazy=[select_notion_database_lazy],
    )

    def _validate_send_to_notion_submission(state_values: dict) -> dict:
        errors = {}
        for block_id, action_id_to_value in state_values.items():
            action_id = list(action_id_to_value.keys())[0]
            value_obj = action_id_to_value[action_id]
            str_value = value_obj.get("value")
            if action_id == "number" and str_value is not None and not str_value.isnumeric():
                errors[block_id] = "This property must be a number"
            if action_id == "url" and str_value is not None and not str_value.startswith("http"):
                errors[block_id] = "This property must be a URL"
            if action_id == "email" and str_value is not None and "@" not in str_value:
                errors[block_id] = "This property must be an email address"
        return errors

    def sent_to_notion_ack(ack: Ack, view: dict):
        errors = _validate_send_to_notion_submission(view["state"]["values"])
        if len(errors) > 0:
            ack(response_action="errors", errors=errors)
            return

        ack(
            response_action="update",
            view={
                "type": "modal",
                "callback_id": "send-to-notion-database",
                "title": {"type": "plain_text", "text": "Send to Notion"},
                "close": {"type": "plain_text", "text": "Close"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ":hourglass: Wait a second. Now sending the data to Notion ...",
                        },
                    }
                ],
            },
        )

    def sent_to_notion_lazy(
        view: dict,
        body: dict,
        say: Say,
        context: BoltContext,
        client: WebClient,
        logger: logging.Logger,
    ):
        errors = _validate_send_to_notion_submission(view["state"]["values"])
        if len(errors) > 0:
            return
        try:
            database_id = json.loads(view["private_metadata"])["notion_database_id"]
            notion = Client(auth=resolve_notion_token(context))
            new_page = send_to_notion(notion, database_id, view["state"]["values"])
            page_url = new_page["url"]
            client.views_update(
                view_id=view["id"],
                view={
                    "type": "modal",
                    "callback_id": "send-to-notion-database",
                    "title": {"type": "plain_text", "text": "Send to Notion"},
                    "close": {"type": "plain_text", "text": "Close"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f":white_check_mark: Your data has been successfully saved!\n\n{page_url}",
                            },
                        }
                    ],
                },
            )
        except Exception as e:
            logger.exception(e)
            client.views_update(
                view_id=view["id"],
                view={
                    "type": "modal",
                    "callback_id": "send-to-notion-database",
                    "title": {"type": "plain_text", "text": "Send to Notion"},
                    "close": {"type": "plain_text", "text": "Close"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": ":x: Saving your data failed for some reason. "
                                "Please contact this app's user support email address :bow:",
                            },
                        }
                    ],
                },
            )
            say(
                channel=context.user_id,
                text=f"I'm sorry for being distracted! This app failed to send your data to Notion (error: {e})\n"
                "Please contact this app's user support email address :bow:",
            )

    app.view("send-to-notion-database")(
        ack=sent_to_notion_ack,
        lazy=[sent_to_notion_lazy],
    )
